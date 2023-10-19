# ActiveClone
Dynamic Multi-Monitor Desktop Cloning. Clone active monitor to Borderless Fullscreen window. Steamlink-like Clone.

ActiveClone is a dynamic multi-monitor desktop cloning tool that enables you to create a fullscreen window on a specified display, which mirrors the screen where the mouse cursor is located. This results in a "dynamic clone" of a multi-monitor setup where the output screen automatically follows the cursor.

utilizes DesktopDuplicationAPI via DXCam
 https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api
 https://github.com/ra1nty/DXcam
 https://github.com/AI-M-BOT/DXcam/
 
## Introduction
I had been using a SteamLink as a KVM and got quite used to this feature. ActiveClone emulates its behavior on an extended KVM screen, providing a convenient way to interact with all your desktops on multiple monitor setups.

## Getting Started
```
usage: activeclone.py [-h] [--display DISPLAY] [--fps FPS] [-show_fps]
options:
  --display DISPLAY  Output display number
  --fps FPS          FPS limit (Default 60)
  --show_fps          Show FPS
```
Toggeling ScollLock on will confine the cursor to the current screen.

## State of Project

This is a first hacky implementation that currently fully works for my use case. However, it's important to note that the project's future is uncertain. Contributions and support from the community are welcome.
While the core functionality is operational, cursor image handling is hacky and does not support DXGI_OUTDUPL_POINTER_SHAPE_TYPE_MASKED_COLOR type cursors.
