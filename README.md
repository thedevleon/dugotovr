# dugotovr - Dual GoPro Toolkit for 180VR
This is a collection of tools (scripts) and 3d printable parts for VR180 content creation using two GoPro 13s with the Ultrawide Lens Mod.

![setup](img/setup.png)

In comparison to the many other offerings (Canon EOS RF 5.2mm Dual Fisheye, Canon EOS RF-S 3.9mm Dual Fisheye, Calf 2/Visinse, SLAM XCAM, etc...) two GoPro's can be easily had for under 1000$, while offering very high resolution 8K (4K per eye) footage in 10 bit, with the highest bitrate among all the consumer options (i.e. Calf, SLAM, etc...) and a 177 degree FoV.

However, the biggest pain points with two separate cameras is synchronization and a complex post-production workflow, which is hopefully made a little bit easier with this collection of tools.

## Tips for shooting with two GoPros
- Use Timecode Sync regularly to keep both cameras in sync. This can be done in the [official gopro app](https://community.gopro.com/s/article/HERO12-Black-Timecode-Sync), or via the [labs firmware](https://gopro.github.io/labs/) + the [QR Code Generators](https://gopro.github.io/labs/control/custom/).
- To get the full resolution and FoV, you need the Max Lens Mod 2.0 / Ultrawide Lens with the following settings:
  - Lens: Standard (do not enable the max / ultrawide lens mode)
  - Framing: 8:7
  - Resolution: 5.3K
  - Frame Rate: 30
  - Digital Lens: Wide (the only option)
  - HyperSmooth: Off
  - Profile: Standard or Log. HDR doesn't work with 5.3K unfortunately.
  
  -> you should be seeing (almost) the full fisheye in the preview, without it being stretched, cut-off or moving when you move the camera.

## Prerequisites
- NVidia GPU and [CUDA toolkit](https://developer.nvidia.com/cuda-toolkit)
- FFmpeg with CUDA support (i.e. ffmpeg-git-full for windows: https://www.gyan.dev/ffmpeg/builds/) or [compiled from source](https://docs.nvidia.com/video-technologies/video-codec-sdk/12.0/ffmpeg-with-nvidia-gpu/index.html)
- Python

Ensure that ffmpeg works with cuda, i.e. make sure this plays one of your gopro clips:
```
ffplay -vcodec hevc_cuvid GX010004.mp4
```
# In a nutshell - from two video files to VR180 video
To convert the raw footage from your GoPros into something you can watch in VR180 with any device, there are a couple of steps that need to happen:
  1. left and right footage clips need to be synchronized to the frame to avoid any ghosting and visual artifacts
  2. the clips need to be put side-by-side
  3. left and right need to be calibrated (i.e. slightly transformed) so that the stereo looks correct
  4. the fisheye footage needs to be remapped into an equirectangular format

On the EOS VR side, this can be done with the EOS VR Utility, however this will cost you 5$ per month for something you can do for free, and only works with Canon Cameras. You also have very little control about the process, and can only adjust basic settings.

Steps 3 and 4 can be done combined and more efficient with an STMap.
To generate such an STMap, you can use the KartaVR Fusion Composition "Dual Fisheye STMap Creation v001".

I recommend to watch the following videos to get a better understanding:
- https://www.youtube.com/watch?v=kwVlVEXg3og
- recent videos from sailing360: https://www.youtube.com/@Sailing360

# Scripts

## sync.py
This script will look through a folder of footage and find matching clips (based on timecode and date/time metadata), trim them so that they are aligned (automatically based on timecode), crop the fisheye into a 1:1 ratio, and combine the clips into a single side-by-side file for further processing. Optionally, this can also perform fisheye to equirectangular conversion (--dewarp), although it is a lot slower than just merging, and also does not allow for stereo calibration. Footage can look "fine" without stereo calibration, but doing it is highly recommended.

**NOTE**: for the script to have any idea which one is the left and which one is the right camera, you will need to have subfolders denoting which clips are left, and which are right.

## dewarp.py
Dewarps and aligns the dual fisheye footage using an STMap.
Multiple options for implementation: ffmpeg + remap (CPU only), ffmpeg + v360 (CPU only), or gstreamer (either gst-nvdewarper or gst-nvivafilter + cv::cuda::remap)

# The Setup™️
2x GoPro Hero 13, FeiyuTech Scorp-C, SIRUI AM-404FL, Zoom H2essential, Movo SMM5-B Shock Mount, a 3D-printed bracket to hold both GoPros securely

# The Workflow™️

Filming
- sync timecode and match settings (iso, shutter, etc) via QRControl
- start recording on audio recorder
- start recording on both GoPros simultaneously via "The Remote" or an app like [GoPro Remote](https://play.google.com/store/apps/details?id=uk.co.purplelabs.gopro_remote)
- use a clapperboard to make audio and video synchronization much easier

Ingress
- Dump footage from both cameras into a folder and adjust the path to contain "left" and "right", i.e. by putting them into left and right subfolders, or including "left" or "right" in the filename.
- Run the `sync.py` script to automatically organize, match, crop, trim, align based on timecode and merge into a single sbs video per pair.

Process (for each combined clip)
- Generate STMap (in DaVinci Fusion) using the "STMap Gen" Composition, or re-use an earlier STMap if you're confident the cameras have not moved. You might have to make a screenshot of the first frame to use in the "Loader", mp4 doesn't seem to work.
- Apply the STMap in DaVinci Fusion using "kvrSuperSTMap" if you need to do stereo calibration, or just STMapper if you did the stereo calibration already when creating the STMap
  
**NOTES**
- The GlobalAlign node (part of kvrSuperSTMap) seems to be a bottleneck. To skip it, use the Center property of kvrCropStereo to calibrate and bake it into the STMap. Then you can create a simpler graph without the GlobalAlign to speed up processing with the STMap.
- If applying the STMap in DaVinci is too slow, you can also use TouchDesigner, see https://kartaverse.github.io/Kartaverse-Docs/#/TouchDesigner.
- It's best to process all footage in Fusion beforehand, and then using only the processed footage in Resolve. That way you're not re-applying the STMap with every render, and can also generate proxies for the processed footage.


## Benchmarks
Performed on a Ryzen 3700X, 32GB RAM, RTX 2080 Super.
I would assume that STMap-based workflows will be greatly accelerated with a better GPU.

### sync.py
- with cuda, without dewarp -> 26 FPS
- with cuda, with dewarp -> 9 FPS

### DaVinci
- dewarped -> 4.5 FPS
- fisheye + GlobalAlign + kvrViewer -> 0.5 FPS
- fisheye + kvrSuperSTMap -> 0.14 FPS 
- fisheye + STMapper (with stereo correction baked-in) -> 1 FPS

# Notes
- Make sure the GoPros are very secure and aligned. If they get loose during your filming, your footage will be ruined. And if they keep moving, you will have to keep calibrating them.
- Doing the conversion from dual fisheye to equirectangular is expensive, and if you don't have the beefiest PC, doing it in Resolve with KartaVRs kvrCreateStereo, kvrCropStereo, kvrViewer, etc... is painfully slow. STMaps will 
- The Ultrawide / Max Lens is waterpoof up to 5m, but won't actually work well underwater due to pesky limitations on how light works underwater. If you want a sharp picture, you need a dome with a decent spacing to the lens.