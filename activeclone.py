import sys

sys.path.append('dxcam_git') #fixme
import dxcam
from dxcam._libs.dxgi import *

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

import re
import win32gui
import win32con
import win32api

import traceback
import numpy as np

import ctypes
from ctypes import windll, Structure, c_ulong, c_wchar, byref, c_long, sizeof
from ctypes.wintypes import RECT, POINT

from functools import cache

import argparse

import time
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

def GetCursorInfo_win32gui():
    pt = POINT()
    flags, hcursor, (x,y) = win32gui.GetCursorInfo()
    pt.x = x
    pt.y = y
    return pt, True if flags == 1 else False, hcursor
 
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

def convert_monochrome_to_rgba(hbmMask, width, height):
    length = width * height
    input = np.frombuffer(hbmMask, dtype=np.uint8)
    byte_indices = np.arange(length) // 8
    bit_positions = 7 - (np.arange(length) % 8)

    and_vals = (input[byte_indices] >> bit_positions) & 1
    xor_vals = (input[byte_indices + length // 8] >> bit_positions) & 1
    rgba_output = np.zeros((length, 4), dtype=np.uint8)
    sub_output = np.zeros((length, 4), dtype=np.uint8)
    rgba_output[np.logical_and(and_vals == 0 , xor_vals == 0)] = [0, 0, 0, 255]     
    rgba_output[np.logical_and(and_vals == 0 , xor_vals == 1)] = [255, 255, 255, 255]  
    sub_output[np.logical_and(and_vals == 1 , xor_vals == 1)] = [255, 255, 255, 255]     #"inverted"
    return (rgba_output,sub_output)

def build_monitors(dxcam_output_info):
    pattern = r'Device\[(\d+)\] Output\[(\d+)\]: szDevice\[(.+?)\]: Res:\((\d+), (\d+)\) Rot:\d+ Primary:(\w+)'
    monitor_info = re.findall(pattern, dxcam_output_info)
    r= []
    for match in monitor_info:
        device_idx = int(match[0])
        output_idx = int(match[1])
        szDevice = match[2]
        width = int(match[3])
        height = int(match[4])
        is_primary = match[5] == 'True'
        r.append((device_idx, output_idx, szDevice, width, height, is_primary))
    return r

def cursorLocker(monitor_handle):
    SLstate = win32api.GetKeyState(win32con.VK_SCROLL)
    if SLstate == -127: #toggled on
        monitorinfo = get_monitor_info(monitor_handle)
        windll.user32.ClipCursor(monitorinfo.rcMonitor)
    elif SLstate == -128: #toggled off
        win32api.ClipCursor()

monitors = build_monitors(dxcam.output_info())
print(*enumerate(monitors), sep='\n')

parser = argparse.ArgumentParser()
parser.add_argument("--display", type=int, default=1, help="Output display number")
parser.add_argument("--fps", type=int, default=60, help="FPS limit (Default 60) 0 to disable")
parser.add_argument("--show_fps", action="store_true", help="Show FPS")
args = parser.parse_args()
parser.print_help()

output_display = args.display
fpslimit = args.fps
show_fps = args.show_fps

# setup pygame/window
pygame.init()
pygameFlags = pygame.NOFRAME |  pygame.FULLSCREEN | pygame.HWSURFACE | pygame.SCALED #crashy without scaled??
window = pygame.display.set_mode((monitors[output_display][3], monitors[output_display][4]), pygameFlags , display=output_display,vsync=0)
win32gui.SetWindowPos(pygame.display.get_wm_info()['window'], win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
clock = pygame.time.Clock()
last_frame_update = time.perf_counter_ns()
pygame.font.init()
font = pygame.font.SysFont('lucidaconsole', 10)

# Initialize dxcam for each display
cameras = {}
for i, (device_idx, output_idx, _, _, _, _) in enumerate(monitors):
    cameras[i] = dxcam.create(device_idx=device_idx, output_idx=output_idx, output_color="BGRA")
    #cameras.append(camera)

cursorcache = {}
def get_cursor_image(cursor,hcursor):
    if cursor.Shape is not None:          
        if hcursor not in cursorcache:
            scursor_i=None
            h=int(cursor.PointerShapeInfo.Height)
            w=int(cursor.PointerShapeInfo.Width)
            if cursor.PointerShapeInfo.Type == 1:  #DXGI_OUTDUPL_POINTER_SHAPE_TYPE DXGI_OUTDUPL_POINTER_SHAPE_TYPE_MONOCHROME
                h = int(cursor.PointerShapeInfo.Height/2)
                bcursor,bcursor_invert = convert_monochrome_to_rgba(cursor.Shape, w,h)
                scursor = pygame.image.frombuffer(bcursor,(w , h),"BGRA")
                scursor_i = pygame.image.frombuffer(bcursor_invert,(w , h),"BGRA")#,(0,0),None, pygame.BLEND_RGBA_SUB
                scoffset= cursor.PointerShapeInfo.HotSpot
            elif cursor.PointerShapeInfo.Type == 2: #DXGI_OUTDUPL_POINTER_SHAPE_TYPE_COLOR
                scursor = pygame.image.frombuffer(cursor.Shape,(w , h),"BGRA")
                scoffset= cursor.PointerShapeInfo.HotSpot
            else: #unhandled DXGI_OUTDUPL_POINTER_SHAPE_TYPE_MASKED_COLOR
                scursor = pygame.Surface((4, 4))
                scursor.draw.rect(window, (255, 0, 0), (0, 0, 4, 4))
                scoffset= POINT(2,2)
            cursorcache[hcursor]={"Surface":scursor,"Offset": scoffset,"Inverted":scursor_i,"Size":(w , h)}
        return cursorcache[hcursor]

grab_shot=False #sadly not much of a difference
s_cursor_background = pygame.Surface((16,16))
try:
    while True:
        # Get the current cursor position to determine the active monitor
        cursor_pos, cursor_visible, hcursor = GetCursorInfo_win32gui()
        monitor_handle = windll.user32.MonitorFromPoint(cursor_pos, MONITOR_DEFAULTTONEAREST)  # returns monitor handle       
        cursorLocker(monitor_handle)
        active_monitor = monitor_id_from_hmonitor(monitor_handle)
        frame_width,frame_height =(monitors[active_monitor][3], monitors[active_monitor][4])
        if (frame_width, frame_height) != window.get_size():
            window = pygame.display.set_mode((frame_width, frame_height), pygameFlags , display=output_display,vsync=0)

        if grab_shot:
            frame = cameras[active_monitor].grab()
            if frame is not None:
                window.get_buffer().write(frame,0)
                last_frame_update = time.perf_counter_ns()
        else:
            if cameras[active_monitor].shot(window._pixels_address) is not None:
                last_frame_update = time.perf_counter_ns()
        cursor = cameras[active_monitor].grab_cursor() 

        # Create a pygame surface from the frame
        #frame_surface = pygame.surfarray.make_surface(frame.transpose(1, 0, 2)) #slow
        #pygame.surfarray.blit_array(window,frame.transpose(1, 0, 2)) #better but still slow
        #window.get_buffer().write(frame,0) #speed winner 
        
        #draw fps
        if show_fps:
            s_main_fps = font.render(str(int(clock.get_fps())), True, "White", "Black")
            update_fps = min(1.0 /((time.perf_counter_ns()-last_frame_update)/ 1e9) , clock.get_fps())
            s_update_fps = font.render(str(update_fps), True, "White", "Black")
            window.blits(blit_sequence=((s_main_fps, (3,15)),(s_update_fps, (3,30))))
            #window.blit(main_fps, (3,15))


        #draw cursor?
        if  cursor_visible == True:
            #cursor_x = cursor.PointerPositionInfo.Position.x #from capture position, has problems when dragging
            #cursor_y = cursor.PointerPositionInfo.Position.y
            monitorinfo = get_monitor_info(monitor_handle)

            cursor_surface = get_cursor_image(cursor,hcursor)
            cursor_x = cursor_pos.x - monitorinfo.rcMonitor.left - cursor_surface["Offset"].x
            cursor_y = cursor_pos.y - monitorinfo.rcMonitor.top - cursor_surface["Offset"].y

            s_cursor_background = pygame.Surface((cursor_surface["Size"][0],cursor_surface["Size"][1]))
            s_cursor_background.blit(window, (0, 0), (cursor_x,cursor_y,cursor_surface["Size"][0],cursor_surface["Size"][1]))

            if  cursor_surface["Inverted"] is not None:
                window.blit(cursor_surface["Inverted"], (cursor_x, cursor_y),None, pygame.BLEND_RGBA_SUB) #todo use 
            window.blit(cursor_surface["Surface"], (cursor_x, cursor_y ))

        pygame.display.flip()
        window.blit(s_cursor_background, (cursor_x, cursor_y ))  #delete cursor from fb
        clock.tick(fpslimit)


        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                for camera in cameras:
                    camera.release()
                exit()

except KeyboardInterrupt:
    pass

for i, camera in cameras.items():
    camera.release()
pygame.quit()
