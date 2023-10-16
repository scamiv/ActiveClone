import sys
sys.path.append('dxcam_git') #fixme
import dxcam
import pygame
import re
import win32gui
import win32con

from ctypes import windll, Structure, c_ulong, c_wchar, byref,c_long, sizeof
from ctypes.wintypes import RECT
    
from functools import cache
from dxcam._libs.dxgi import *

#settings
output_display = 1
fpslimit=60
show_fps=True;

class MONITORINFOEXW(Structure):
    _fields_ = [
        ("cbSize", c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", c_ulong),
        ("szDevice", c_wchar*32),
    ]

# Define the constants for MonitorFromPoint
MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTOPRIMARY = 1
MONITOR_DEFAULTTONEAREST = 2

class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]

def queryMousePosition_ctypes():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt

def queryMousePosition_win32gui():
    pt = POINT()
    flags, hcursor, (x,y) = win32gui.GetCursorInfo()
    pt.x = x
    pt.y = y
    return pt
 
@cache
def monitor_id_from_hmonitor (hmonitor):
    devicePath = dxcam.util.io.get_monitor_name_by_handle(hmonitor).szDevice  
    active_monitor = 0
    for i, (_, _, szDevice, _, _, _) in enumerate(monitors):
        if szDevice == devicePath:
            active_monitor = i
            break
    return active_monitor

@cache
def get_monitor_info(monitor_id):
    monitorinfo = MONITORINFOEXW()
    monitorinfo.cbSize = sizeof(MONITORINFOEXW) #104
    monitorinfo.dwFlags = MONITOR_DEFAULTTONEAREST 
    windll.user32.GetMonitorInfoW(monitor_id, byref(monitorinfo))
    return monitorinfo   

# Initialize Pygame
pygame.init()

output_info = dxcam.output_info() #add proper output...
pattern = r'Device\[(\d+)\] Output\[(\d+)\]: szDevice\[(.+?)\]: Res:\((\d+), (\d+)\) Rot:\d+ Primary:(\w+)'
monitor_info = re.findall(pattern, output_info)


monitors = []
for match in monitor_info:
    device_idx = int(match[0])
    output_idx = int(match[1])
    szDevice = match[2]
    width = int(match[3])
    height = int(match[4])
    is_primary = match[5] == 'True'
    monitors.append((device_idx, output_idx, szDevice, width, height, is_primary))
print(*enumerate(monitors), sep='\n')

# setup pygame/window
window = pygame.display.set_mode((0, 0), pygame.NOFRAME | pygame.HWSURFACE , display=output_display,vsync=0)
win32gui.SetWindowPos(pygame.display.get_wm_info()['window'], win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
clock = pygame.time.Clock()
pygame.font.init()
font = pygame.font.SysFont('lucidaconsole', 10)

# Initialize dxcam for each display
cameras = []
for device_idx, output_idx, _, _, _, _ in monitors:
    camera = dxcam.create(device_idx=device_idx, output_idx=output_idx, output_color="BGRA")
    cameras.append(camera)


cursor = ac_Cursor()
try:
    while True:
        # Get the current cursor position to determine the active monitor
        mouse_pos = queryMousePosition_ctypes()
        monitor_id = windll.user32.MonitorFromPoint(mouse_pos, MONITOR_DEFAULTTONEAREST)  # returns monitor handle
        active_monitor = monitor_id_from_hmonitor(monitor_id)

        if active_monitor is not None:
            frame = cameras[active_monitor].grab()  # grab frame from active_monitor 
            cursor = cameras[active_monitor].grab_cursor() 

            if frame is not None: 
                frame_height,frame_width,_ = frame.shape #rotated
                #todo, adjust output to input resolutionQ
                if (frame_width, frame_height) != window.get_size():
                    window = pygame.display.set_mode((frame_width, frame_height), pygame.NOFRAME | pygame.HWSURFACE , display=output_display,vsync=0)

                monitorinfo = get_monitor_info(monitor_id)
                monitor_width = monitorinfo.rcMonitor.right - monitorinfo.rcMonitor.left
                monitor_height = monitorinfo.rcMonitor.bottom - monitorinfo.rcMonitor.top

                # Calculate the cursor position relative to the active monitor's top/left, TODO: DXGI_OUTDUPL_POINTER_POSITION should give the right value
                cursor_x = mouse_pos.x - monitorinfo.rcMonitor.left
                cursor_y = mouse_pos.y - monitorinfo.rcMonitor.top
                
                #todo Scale position to surface?
                #print(window.get_size())
                #print(frame_width, frame_height)

                # Create a pygame surface from the frame
                #frame_surface = pygame.surfarray.make_surface(frame.transpose(1, 0, 2)) #slow
                #pygame.surfarray.blit_array(window,frame.transpose(1, 0, 2)) #better but still slow
                window.get_buffer().write(frame,0) #speed winner 
                
                #draw fps
                if show_fps:
                    text_surface = font.render(str(int(clock.get_fps())), True, "White")
                    window.blit(text_surface, (3,15))
                
                #draw cursor
                try:
                    #print(cursor)
                    if cursor.Shape is not None:
                        #scursor = pygame.image.frombytes(bytes(cursor),(32,32),"RGBA",False)
                        #DXGI_OUTDUPL_POINTER_SHAPE_TYPE 
                        if cursor.PointerShapeInfo.Type == 1: #DXGI_OUTDUPL_POINTER_SHAPE_TYPE_MONOCHROME
                            #todo
                            scursor = None
                        elif cursor.PointerShapeInfo.Type == 2: #DXGI_OUTDUPL_POINTER_SHAPE_TYPE_COLOR
                            scursor = pygame.image.frombuffer(cursor.Shape,(cursor.PointerShapeInfo.Width , cursor.PointerShapeInfo.Height),"BGRA")
                            window.blit(scursor, (cursor_x,cursor_y))
                except Exception as e:
                    # Draw "cursor"
                    pygame.draw.rect(window, (255, 0, 0), (cursor_x - 2, cursor_y - 2, 4, 4))
                    print("cursor error:",e)

                #Display
                #window.blit(frame_surface, (0, 0)) #when using make_surface
                pygame.display.flip()               
                clock.tick(fpslimit)


        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                for camera in cameras:
                    camera.release()
                exit()

except KeyboardInterrupt:
    pass

# Clean up
for camera in cameras:
    camera.release()
pygame.quit()