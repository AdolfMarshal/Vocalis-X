from pywinauto import Desktop

print("OpenUtau window candidates:")
for w in Desktop(backend="uia").windows():
    title = w.window_text()
    if "OpenUtau" in title:
        print("-", title)
