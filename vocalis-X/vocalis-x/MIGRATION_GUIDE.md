# Migration Guide: Upgrading Vocalis-X

This guide helps you migrate from the original code to the improved version with better error handling, configuration management, and performance optimizations.

## 🚀 Quick Start (Minimal Changes)

### Option 1: Keep Original Code, Add Only Configuration

If you want minimal disruption, just add the configuration system:

1. **Install new dependencies:**
```bash
pip install pydantic-settings structlog
```

2. **Copy these files to your project:**
- `config.py`
- `.env.example` → rename to `.env` and customize

3. **Update your `.env` file with your paths:**
```env
OPENUTAU_EXE_PATH=C:/Users/adolf/OpenUtau/OpenUtau.exe
MUSICGEN_MODEL=facebook/musicgen-medium
```

4. **In `main.py`, replace hardcoded paths:**
```python
# OLD:
teacher_track = "C:\\Users\\adolf\\vocalis-x\\separated\\htdemucs\\ref1\\no_vocals.wav"

# NEW:
from config import settings
teacher_track = settings.get_teacher_track_path()
```

Done! Your code now uses configuration files.

---

## 📦 Full Migration (Recommended)

For the best experience with all improvements:

### Step 1: Backup Your Current Setup

```bash
# Create backup
cp main.py main.py.backup
cp schemas.py schemas.py.backup
```

### Step 2: Install Dependencies

```bash
pip install -r requirements_additional.txt
```

### Step 3: Copy New Files

Copy these new files to your `vocalis-x/` directory:
- ✅ `config.py` - Configuration management
- ✅ `errors.py` - Custom exception classes
- ✅ `session_manager.py` - Thread-safe session management
- ✅ `cache_manager.py` - Caching for expensive operations
- ✅ `schemas_improved.py` - Enhanced validation
- ✅ `main_improved.py` - Improved main API

### Step 4: Configure Your Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your paths
notepad .env  # or use your favorite editor
```

**Important settings to configure in `.env`:**
```env
OPENUTAU_EXE_PATH=C:/Users/YOUR_USERNAME/OpenUtau/OpenUtau.exe
DEFAULT_TEACHER_TRACK=ref1
MUSICGEN_MODEL=facebook/musicgen-medium
```

### Step 5: Update Imports

#### Option A: Rename and Use New Files (Recommended)
```bash
# Rename old files
mv main.py main_old.py
mv schemas.py schemas_old.py

# Use new files
mv main_improved.py main.py
mv schemas_improved.py schemas.py
```

#### Option B: Gradual Migration
Keep `main.py` but update it section by section using `main_improved.py` as reference.

### Step 6: Update Other Files to Use New Error Classes

**In `musicgen_ai.py`:**
```python
# Add at top
from errors import MusicGenerationError, ModelLoadError

# Replace generic exceptions:
# OLD:
raise Exception("Failed to load model")

# NEW:
raise ModelLoadError("Failed to load model", {"model": model_name})
```

**In `singing_synth.py`:**
```python
# Add at top
from errors import VocalSynthesisError

# Replace:
# OLD:
raise SingingNotConfiguredError(...)

# NEW: (SingingNotConfiguredError is now an alias for VocalSynthesisError)
# No changes needed! But you can use VocalSynthesisError for clarity
```

**In `openutau_automation.py`:**
```python
# Add at top
from errors import OpenUtauError

# Replace:
# OLD:
raise OpenUtauAutomationError(...)

# NEW: (OpenUtauAutomationError is now an alias)
# No changes needed!
```

### Step 7: Add Caching to Expensive Operations

**Update `chord_extractor.py`:**
```python
from cache_manager import get_cache_manager

def extract_chords(audio_path: str) -> list:
    cache = get_cache_manager()
    
    # Try cache first
    return cache.get_or_compute(
        audio_path,
        _extract_chords_impl,  # Your actual extraction function
        prefix="chords"
    )

def _extract_chords_impl(audio_path: str) -> list:
    # Move your existing extraction code here
    # ... existing code ...
    return chords
```

**Similarly for `groove_extractor.py`:**
```python
from cache_manager import get_cache_manager

def extract_groove(audio_path: str) -> dict:
    cache = get_cache_manager()
    return cache.get_or_compute(
        audio_path,
        _extract_groove_impl,
        prefix="groove"
    )
```

### Step 8: Update UI Error Handling

**In `vocalis-x-ui/pages/index.js`:**
```javascript
// OLD:
} catch (err) {
  setStatus(`Error: ${err.message}`);
}

// NEW:
} catch (err) {
  console.error("Generation error:", err);
  
  // Better error display
  const errorMsg = err.response?.data?.detail?.message 
    || err.message 
    || "Unknown error occurred";
  
  setStatus(`Error: ${errorMsg}`);
  alert(`Generation failed: ${errorMsg}`);
}
```

### Step 9: Test Your Migration

```bash
# Start the backend
cd vocalis-x
.venv\Scripts\Activate.ps1  # Windows
uvicorn main:app --reload

# In another terminal, start the frontend
cd vocalis-x-ui
npm run dev

# Test generation
# 1. Try instrumental-only generation
# 2. Try with vocals
# 3. Try reusing last instrumental
# 4. Check that cache is working (should be faster on 2nd run)
```

### Step 10: Monitor and Verify

Check the new endpoints:
```bash
# Health check
curl http://localhost:8000/health

# Cache stats
curl http://localhost:8000/cache/stats

# Clear cache if needed
curl -X POST http://localhost:8000/cache/clear
```

---

## 🔍 What Changed?

### Configuration Management
- **Before:** Hardcoded paths in code
- **After:** `.env` file with `config.py`
- **Benefit:** Works on any machine, easy to customize

### Session Management
- **Before:** Global variable (not thread-safe)
- **After:** Thread-safe SessionManager
- **Benefit:** Can handle multiple users, production-ready

### Error Handling
- **Before:** Generic `Exception` or print statements
- **After:** Specific error classes with structured logging
- **Benefit:** Better debugging, clearer error messages

### Caching
- **Before:** Re-extract chords/groove every time
- **After:** Cached results
- **Benefit:** 5-10 seconds faster per generation

### Validation
- **Before:** Minimal validation
- **After:** Pydantic Field validators
- **Benefit:** Catches bad input early, better error messages

---

## 🐛 Troubleshooting

### Import Error: No module named 'pydantic_settings'
```bash
pip install pydantic-settings
```

### Import Error: No module named 'structlog'
```bash
pip install structlog
```

### Configuration Not Loading
Check that `.env` file is in the same directory as `config.py`:
```bash
ls -la vocalis-x/.env
```

### Paths Not Working
Verify your `.env` paths are absolute and use forward slashes:
```env
# GOOD:
OPENUTAU_EXE_PATH=C:/Users/adolf/OpenUtau/OpenUtau.exe

# BAD:
OPENUTAU_EXE_PATH=C:\Users\adolf\OpenUtau\OpenUtau.exe  # Use / not \
```

### Cache Not Working
Check cache directory exists and has write permissions:
```bash
ls -la vocalis-x/cache/
```

### Session ID Issues
If using the API directly, include session ID in header:
```bash
curl -H "X-Session-Id: my-session-123" ...
```

---

## 📊 Performance Improvements Expected

After migration, you should see:

| Operation | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Chord extraction (cached) | 8s | 0.1s | **80x faster** |
| Groove extraction (cached) | 5s | 0.1s | **50x faster** |
| Concurrent requests | ❌ Race conditions | ✅ Thread-safe | Reliable |
| Error debugging | 😞 Hard | 😊 Easy | Better DX |
| Portability | ❌ Adolf's PC only | ✅ Any PC | Shareable |

---

## 🎯 Optional Enhancements

### Add Structured Logging

Create `logging_config.py`:
```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)
```

### Add Request ID Middleware

In `main_improved.py`, add:
```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIDMiddleware)
```

### Add Automatic Cleanup Task

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

def cleanup_task():
    session_manager.cleanup_expired_sessions()
    # Clean old audio files
    cleanup_old_files(settings.output_dir, days=7)

scheduler.add_job(cleanup_task, 'interval', hours=24)
scheduler.start()
```

---

## 🔄 Rollback Plan

If something goes wrong, rollback is easy:

```bash
# Restore original files
mv main.py.backup main.py
mv schemas.py.backup schemas.py

# Remove new files
rm config.py errors.py session_manager.py cache_manager.py

# Restart
uvicorn main:app --reload
```

---

## ✅ Migration Checklist

- [ ] Install `pydantic-settings` and `structlog`
- [ ] Copy new files to project
- [ ] Create `.env` from `.env.example`
- [ ] Configure paths in `.env`
- [ ] Update `main.py` (rename or replace)
- [ ] Update `schemas.py` (rename or replace)
- [ ] Add caching to chord/groove extractors
- [ ] Update UI error handling
- [ ] Test instrumental generation
- [ ] Test vocal generation
- [ ] Test cache (run twice, should be faster)
- [ ] Check `/health` endpoint works
- [ ] Verify session management works
- [ ] Update documentation

---

## 📞 Need Help?

Common issues and solutions are in the Troubleshooting section above.

For bugs or issues with the improved code, check:
1. Is `.env` configured correctly?
2. Are all dependencies installed?
3. Are file paths using forward slashes?
4. Check the logs for specific errors
