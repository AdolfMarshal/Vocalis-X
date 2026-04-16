"""
Utility functions for cleaning up old files and maintaining the system
"""
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import structlog

logger = structlog.get_logger()


def get_file_age_days(file_path: Path) -> float:
    """Get file age in days"""
    mtime = file_path.stat().st_mtime
    age_seconds = datetime.now().timestamp() - mtime
    return age_seconds / 86400


def cleanup_old_files(
    directory: Path, 
    days: int = 7,
    pattern: str = "*.wav",
    dry_run: bool = False
) -> dict:
    """
    Delete files older than specified days
    
    Args:
        directory: Directory to clean
        days: Delete files older than this many days
        pattern: Glob pattern for files to clean
        dry_run: If True, don't actually delete, just report
    
    Returns:
        Dictionary with cleanup stats
    """
    directory = Path(directory)
    
    if not directory.exists():
        logger.warning("cleanup_directory_not_found", path=str(directory))
        return {"deleted": 0, "freed_mb": 0, "skipped": 0}
    
    deleted_count = 0
    freed_bytes = 0
    skipped_count = 0
    
    for file_path in directory.rglob(pattern):
        if not file_path.is_file():
            continue
        
        try:
            age_days = get_file_age_days(file_path)
            
            if age_days > days:
                file_size = file_path.stat().st_size
                
                if dry_run:
                    logger.info("would_delete",
                              file=str(file_path),
                              age_days=round(age_days, 1),
                              size_mb=round(file_size / 1024 / 1024, 2))
                    deleted_count += 1
                    freed_bytes += file_size
                else:
                    file_path.unlink()
                    logger.info("deleted_old_file",
                              file=str(file_path),
                              age_days=round(age_days, 1),
                              size_mb=round(file_size / 1024 / 1024, 2))
                    deleted_count += 1
                    freed_bytes += file_size
            else:
                skipped_count += 1
                
        except Exception as e:
            logger.error("cleanup_error",
                        file=str(file_path),
                        error=str(e))
            continue
    
    result = {
        "deleted": deleted_count,
        "freed_mb": round(freed_bytes / 1024 / 1024, 2),
        "skipped": skipped_count,
        "dry_run": dry_run
    }
    
    logger.info("cleanup_complete", **result)
    return result


def cleanup_empty_directories(directory: Path, dry_run: bool = False) -> int:
    """Remove empty directories recursively"""
    directory = Path(directory)
    removed_count = 0
    
    for dirpath in sorted(directory.rglob("*"), reverse=True):
        if not dirpath.is_dir():
            continue
        
        try:
            # Check if empty
            if not any(dirpath.iterdir()):
                if dry_run:
                    logger.info("would_remove_empty_dir", path=str(dirpath))
                else:
                    dirpath.rmdir()
                    logger.info("removed_empty_dir", path=str(dirpath))
                removed_count += 1
        except Exception as e:
            logger.error("error_removing_dir", path=str(dirpath), error=str(e))
    
    return removed_count


def get_directory_size(directory: Path) -> dict:
    """Get total size and file count for directory"""
    directory = Path(directory)
    
    total_size = 0
    file_count = 0
    
    for file_path in directory.rglob("*"):
        if file_path.is_file():
            total_size += file_path.stat().st_size
            file_count += 1
    
    return {
        "path": str(directory),
        "total_mb": round(total_size / 1024 / 1024, 2),
        "file_count": file_count
    }


def cleanup_by_size(
    directory: Path,
    max_size_mb: float,
    pattern: str = "*.wav",
    dry_run: bool = False
) -> dict:
    """
    Delete oldest files until directory is under max size
    
    Args:
        directory: Directory to clean
        max_size_mb: Maximum directory size in MB
        pattern: Glob pattern for files to clean
        dry_run: If True, don't actually delete
    
    Returns:
        Dictionary with cleanup stats
    """
    directory = Path(directory)
    
    # Get current size
    current_stats = get_directory_size(directory)
    current_size_mb = current_stats["total_mb"]
    
    if current_size_mb <= max_size_mb:
        logger.info("cleanup_not_needed",
                   current_mb=current_size_mb,
                   max_mb=max_size_mb)
        return {"deleted": 0, "freed_mb": 0}
    
    # Get all files sorted by modification time (oldest first)
    files = []
    for file_path in directory.rglob(pattern):
        if file_path.is_file():
            files.append((file_path, file_path.stat().st_mtime))
    
    files.sort(key=lambda x: x[1])  # Sort by mtime
    
    deleted_count = 0
    freed_bytes = 0
    
    for file_path, mtime in files:
        if current_size_mb <= max_size_mb:
            break
        
        try:
            file_size = file_path.stat().st_size
            
            if dry_run:
                logger.info("would_delete",
                          file=str(file_path),
                          size_mb=round(file_size / 1024 / 1024, 2))
            else:
                file_path.unlink()
                logger.info("deleted_to_free_space",
                          file=str(file_path),
                          size_mb=round(file_size / 1024 / 1024, 2))
            
            deleted_count += 1
            freed_bytes += file_size
            current_size_mb -= file_size / 1024 / 1024
            
        except Exception as e:
            logger.error("cleanup_error",
                        file=str(file_path),
                        error=str(e))
    
    return {
        "deleted": deleted_count,
        "freed_mb": round(freed_bytes / 1024 / 1024, 2),
        "new_size_mb": round(current_size_mb, 2),
        "dry_run": dry_run
    }


def archive_old_files(
    source_dir: Path,
    archive_dir: Path,
    days: int = 30,
    pattern: str = "*.wav"
) -> dict:
    """
    Move old files to archive directory instead of deleting
    """
    source_dir = Path(source_dir)
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    moved_count = 0
    moved_bytes = 0
    
    for file_path in source_dir.rglob(pattern):
        if not file_path.is_file():
            continue
        
        try:
            age_days = get_file_age_days(file_path)
            
            if age_days > days:
                # Create same directory structure in archive
                relative_path = file_path.relative_to(source_dir)
                archive_path = archive_dir / relative_path
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                
                file_size = file_path.stat().st_size
                
                # Move file
                shutil.move(str(file_path), str(archive_path))
                
                logger.info("archived_file",
                          source=str(file_path),
                          destination=str(archive_path),
                          age_days=round(age_days, 1))
                
                moved_count += 1
                moved_bytes += file_size
                
        except Exception as e:
            logger.error("archive_error",
                        file=str(file_path),
                        error=str(e))
    
    return {
        "archived": moved_count,
        "archived_mb": round(moved_bytes / 1024 / 1024, 2)
    }


def get_storage_report(base_dir: Path) -> dict:
    """Get comprehensive storage report"""
    base_dir = Path(base_dir)
    
    report = {
        "base_directory": str(base_dir),
        "timestamp": datetime.now().isoformat(),
        "directories": {}
    }
    
    # Check common directories
    subdirs = ["output", "cache", "separated", "output/openutau"]
    
    for subdir in subdirs:
        dir_path = base_dir / subdir
        if dir_path.exists():
            report["directories"][subdir] = get_directory_size(dir_path)
    
    # Calculate total
    total_mb = sum(
        d["total_mb"] 
        for d in report["directories"].values()
    )
    total_files = sum(
        d["file_count"] 
        for d in report["directories"].values()
    )
    
    report["total_mb"] = round(total_mb, 2)
    report["total_files"] = total_files
    
    return report


if __name__ == "__main__":
    """Command-line interface for cleanup utilities"""
    import argparse
    from config import settings
    
    parser = argparse.ArgumentParser(description="Vocalis-X Cleanup Utilities")
    parser.add_argument("command", choices=["cleanup", "report", "archive"],
                       help="Command to run")
    parser.add_argument("--days", type=int, default=7,
                       help="Delete files older than N days")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be deleted without deleting")
    parser.add_argument("--pattern", default="*.wav",
                       help="File pattern to match")
    parser.add_argument("--max-size", type=float, default=None,
                       help="Max directory size in MB")
    
    args = parser.parse_args()
    
    if args.command == "cleanup":
        if args.max_size:
            result = cleanup_by_size(
                settings.output_dir,
                args.max_size,
                args.pattern,
                args.dry_run
            )
        else:
            result = cleanup_old_files(
                settings.output_dir,
                args.days,
                args.pattern,
                args.dry_run
            )
        print(f"Cleanup result: {result}")
        
    elif args.command == "report":
        report = get_storage_report(settings.base_dir)
        print("\n=== Storage Report ===")
        print(f"Total: {report['total_mb']} MB, {report['total_files']} files")
        print("\nBy Directory:")
        for name, stats in report["directories"].items():
            print(f"  {name}: {stats['total_mb']} MB ({stats['file_count']} files)")
        
    elif args.command == "archive":
        archive_dir = settings.base_dir / "archive"
        result = archive_old_files(
            settings.output_dir,
            archive_dir,
            args.days,
            args.pattern
        )
        print(f"Archive result: {result}")
