"""
Caching system for expensive operations (chord extraction, groove analysis, etc.)
"""
import json
import hashlib
from pathlib import Path
from typing import Any, Callable, Optional
from datetime import datetime
import shutil


class CacheManager:
    """Manages file-based caching for expensive operations"""
    
    def __init__(self, cache_dir: str = "cache", max_size_mb: int = 1000):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_mb = max_size_mb
    
    def _get_file_hash(self, file_path: str) -> str:
        """Generate hash from file path and modification time"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Combine path and mtime for cache key
        mtime = path.stat().st_mtime
        cache_key = f"{file_path}_{mtime}"
        
        return hashlib.md5(cache_key.encode()).hexdigest()
    
    def _get_cache_path(self, cache_key: str, prefix: str = "cache") -> Path:
        """Get path to cache file"""
        return self.cache_dir / f"{prefix}_{cache_key}.json"
    
    def get(self, file_path: str, prefix: str = "cache") -> Optional[Any]:
        """Get cached data for file"""
        try:
            cache_key = self._get_file_hash(file_path)
            cache_path = self._get_cache_path(cache_key, prefix)
            
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                
                # Touch file to update access time
                cache_path.touch()
                
                return data.get('result')
        except Exception as e:
            print(f"Cache get error: {e}")
            return None
    
    def set(self, file_path: str, data: Any, prefix: str = "cache"):
        """Cache data for file"""
        try:
            cache_key = self._get_file_hash(file_path)
            cache_path = self._get_cache_path(cache_key, prefix)
            
            cache_data = {
                'file_path': str(file_path),
                'cached_at': datetime.now().isoformat(),
                'result': data
            }
            
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            # Cleanup if cache is too large
            self._cleanup_if_needed()
            
        except Exception as e:
            print(f"Cache set error: {e}")
    
    def get_or_compute(
        self, 
        file_path: str, 
        compute_func: Callable, 
        prefix: str = "cache",
        force_recompute: bool = False
    ) -> Any:
        """Get cached data or compute and cache it"""
        
        if not force_recompute:
            cached = self.get(file_path, prefix)
            if cached is not None:
                print(f"✅ Cache hit for {prefix}: {Path(file_path).name}")
                return cached
        
        print(f"🔄 Computing {prefix} for {Path(file_path).name}")
        result = compute_func(file_path)
        
        self.set(file_path, result, prefix)
        
        return result
    
    def clear(self, prefix: Optional[str] = None):
        """Clear cache (optionally by prefix)"""
        if prefix:
            pattern = f"{prefix}_*.json"
        else:
            pattern = "*.json"
        
        deleted = 0
        for cache_file in self.cache_dir.glob(pattern):
            cache_file.unlink()
            deleted += 1
        
        print(f"🗑️ Cleared {deleted} cache files")
    
    def get_cache_size_mb(self) -> float:
        """Get total cache size in MB"""
        total_bytes = sum(
            f.stat().st_size 
            for f in self.cache_dir.rglob("*") 
            if f.is_file()
        )
        return total_bytes / (1024 * 1024)
    
    def _cleanup_if_needed(self):
        """Remove oldest cache files if cache is too large"""
        current_size = self.get_cache_size_mb()
        
        if current_size > self.max_size_mb:
            print(f"⚠️ Cache size {current_size:.1f}MB exceeds limit {self.max_size_mb}MB")
            
            # Get all cache files sorted by access time
            cache_files = sorted(
                self.cache_dir.glob("*.json"),
                key=lambda f: f.stat().st_atime
            )
            
            # Remove oldest files until under limit
            for cache_file in cache_files:
                cache_file.unlink()
                current_size = self.get_cache_size_mb()
                
                if current_size <= self.max_size_mb * 0.8:  # Leave 20% buffer
                    break
            
            print(f"✅ Cache cleaned up to {current_size:.1f}MB")


# Global cache manager instance
_cache_manager = None


def get_cache_manager() -> CacheManager:
    """Get or create global cache manager"""
    global _cache_manager
    if _cache_manager is None:
        from config import settings
        _cache_manager = CacheManager(
            cache_dir=str(settings.cache_dir),
            max_size_mb=settings.max_cache_size_mb
        )
    return _cache_manager
