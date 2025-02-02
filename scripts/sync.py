import subprocess
import os
import sys
import argparse
import glob
from datetime import datetime
from datetime import timedelta
from timecode import Timecode

from util import *

def match_videos(video_data):
    """
    Matches videos into pairs based on creation time.

    :param video_data: Dictionary containing video metadata.
    :return: List of video pairs.
    """
    # Sort videos by creation time
    sorted_videos = sorted(video_data.items(), key=lambda x: x[1]["creation_time"])
    video_pairs = []

    # calculate the time difference between each video, skip videos that are too far apart
    # otherwise, match videos into pairs
    for i in range(1, len(sorted_videos)):
        video1 = sorted_videos[i - 1]
        video2 = sorted_videos[i]
        time_diff = video2[1]["creation_time"] - video1[1]["creation_time"]
        if time_diff > timedelta(seconds=5): # Skip videos that are more than 5 seconds apart
            print(
                f"Skipping {video1[0]} and {video2[0]} pair due to large time difference: {time_diff}"
            )
        elif video1[1]["fps"] != video2[1]["fps"]: # Skip videos with different frame rates
            print(
                f"Skipping {video1[0]} and {video2[0]} pair due to different frame rates: {video1[1]['fps']} vs {video2[1]['fps']}"
            )
        else:

            # Check that the videos are left and right sides
            if video1[1]["side"] == video2[1]["side"]:
                print(f"Skipping {video1[0]} and {video2[0]} pair as they are both {video1[1]['side']} sides.")
                continue

            # make sure that the first video is left and the second video is right, otherwise swap them
            if video1[1]["side"] == "right":
                video1, video2 = video2, video1

            video_pairs.append((video1, video2))

    return video_pairs


def process_videos(video1, video2, start_sec1, start_sec2, output_file, tc, crop, dewarp, cuda):
    cmd = []

    # additional accelerations to look into
    # hstack_vaapi, hstack_qsv

    # alternatives to ss, as it seems not too accurate
    # put -ss after -i -> didn't seem to work at all
    # trim filter: 'trim=start_frame=n' -> couldn't get that to work as expected, only when setstp was also set, which severely reduced the bitrate for some odd reason
    # select filter: 'select=gte(n\,100)' -> not tried yet.

    # v360 options
    # id_fov, ih_fov, iv_fov, d_fov, h_fov, v_fov, in_stereo, out_stereo
    # alpha_mask (creates a yuva420p stream, which is not supported by hevc_nvenc)
    # interp: nearest, linear, cubic, lanczos, spline16, gauss, mitchell (default is linear)
    # nearest is the fastest, but produces very jagged edges
    # lanczos produces pixel errors and is relatively slow
    # cubic is also slow

    if cuda:

        # Unfortunate limitations of ffmpeg with CUDA acceleration
        # overlay_cuda does not support 10-bit video (p010le), so we can't use it and need to do hstack on the CPU instead, uploading and downloading the frames to and from the GPU in between 
        # hevc_nvenc only supports up to 8K resolution (8192), so we need to crop the video to 1:1 before merging
        # hwdownload does not support yuvj420p, so we need to force format=p010le at the scale_cuda filter (GPLog is apparently yuvj420p)
        # v360 only supports yuv420p10le and yuvj420p
        # yuv420p10le == p010le (apparently, see https://www.reddit.com/r/ffmpeg/comments/c1im2i/encode_4k_hdr_pixel_format/)
        


        filter_complex = ""
        if crop and dewarp: # around 8.5 FPS
            filter_complex = f"[0:v] scale_cuda=4096:4096:format=p010le [l]; [1:v] scale_cuda=4096:4096:format=p010le [r]; [l] hwdownload,format=p010le [ls]; [r] hwdownload,format=p010le [rs]; [ls] format=p010le,format=yuv420p10le [lss]; [rs] format=p010le,format=yuv420p10le [rss]; [lss][rss] hstack=inputs=2 [out]; [out] v360=fisheye:hequirect:ih_fov=177:iv_fov=177:in_stereo=sbs:out_stereo=sbs [dewarp]; [dewarp] hwupload_cuda" 
        if crop and not dewarp: # around 23 FPS
            filter_complex = f"[0:v] scale_cuda=4096:4096:format=p010le [l]; [1:v] scale_cuda=4096:4096:format=p010le [r]; [l] hwdownload,format=p010le [ls]; [r] hwdownload,format=p010le[rs]; [ls][rs] hstack=inputs=2 [out]; [out] hwupload_cuda"
        if not crop:
            sys.exit("CUDA acceleration requires cropping, as nvenc only supports up to a max width of 8192.")

        cmd = [
            "ffmpeg",
            "-hwaccel",
            "cuda",
            "-hwaccel_output_format",
            "cuda",
            "-c:v",
            "hevc_cuvid",
            "-crop" if crop else "",
            "0x0x332x332" if crop else "",
            "-ss",
            f"{start_sec1:.6f}",
            "-i",
            video1,
            "-hwaccel",
            "cuda",
            "-hwaccel_output_format",
            "cuda",
            "-c:v",
            "hevc_cuvid",
            "-crop" if crop else "",
            "0x0x332x332" if crop else "",
            "-ss",
            f"{start_sec2:.6f}",
            "-i",
            video2,
            "-shortest", # stop encoding when the shortest input ends
            "-filter_complex",
            filter_complex, 
            "-metadata",
            f"timecode={tc}",  # Set new timecode
            "-c:a:0",
            "copy",
            "-c:v",
            "hevc_nvenc",
            "-b:v",
            "200M", # TODO tune this
            output_file
        ]

    else:

        filter_complex = ""
        if crop and dewarp:
            filter_complex = "[0:v] crop=4648:4648 [l] ; [1:v] crop=4648:4648 [r] ; [l][r] hstack=inputs=2 [out]; [out] v360=fisheye:hequirect:ih_fov=177:iv_fov=177:in_stereo=sbs:out_stereo=sbs"
        if crop and not dewarp:
            filter_complex = "[0:v] crop=4648:4648 [l] ; [1:v] crop=4648:4648 [r] ; [l][r] hstack=inputs=2 [out]"
        if not crop and dewarp:
            filter_complex = "[l][r] hstack=inputs=2; v360=fisheye:hequirect:ih_fov=177:iv_fov=177:in_stereo=sbs:out_stereo=sbs"
        if not crop and not dewarp:
            filter_complex = "[l][r] hstack=inputs=2"

        cmd = [
            "ffmpeg",
            "-ss",
            f"{start_sec1:.6f}",
            "-i",
            video1,
            "-ss",
            f"{start_sec2:.6f}",
            "-i",
            video2,
            "-shortest", # stop encoding when the shortest input ends
            "-filter_complex",
            filter_complex,
            "-metadata",
            f"timecode={tc}",  # Set new timecode
            "-c:a:0",
            "copy",
            "-c:v",
            "libx265",
            "-crf",
            "18", # default is 28
            output_file
        ]

    print(" ".join(cmd))

    try:
        print(f"Clipping {video1} and {video2} -> {output_file}")
        subprocess.run(cmd, check=True)
        print(f"Successfully clipped and merged {output_file}\n")
    except subprocess.CalledProcessError as e:
        print(f"Error clipping and merging {video1} and {video2}: {e.stderr}")
        sys.exit(1)

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("ingress", help="the path to ingress from")
    parser.add_argument("egress", help="the path to egress to")
    parser.add_argument("-o", "--organize", help="create a folder structure of year-mm-dd/ at the egress", action="store_true", default=True)
    parser.add_argument("-c", "--crop", help="crop the 8:7 video to 1:1 before merging", action="store_true", default=True)
    parser.add_argument("-d", "--dewarp", help="dewarp the fisheye video to VR180", action="store_true", default=False)
    parser.add_argument("--cuda", help="use CUDA accelerated operations", action="store_true", default=True)
    parser.add_argument('--no-cuda', dest='cuda', action='store_false')

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    ingress = args.ingress
    egress = args.egress
    organize = args.organize
    crop = args.crop
    dewarp = args.dewarp
    cuda = args.cuda

    # check if the ingress directory exists
    if not os.path.exists(ingress):
        print(f"The ingress directory {ingress} does not exist.")
        sys.exit(1)
    
    # check if the egress directory exists, or create it
    if not os.path.exists(egress):
        os.makedirs(egress)
        print(f"The egress directory {egress} does not exist. Created it.")

    # Get all video files in the ingress directory
    videos = glob.glob(os.path.join(ingress, "*/*.mp4"))

    if len(videos) < 2:
        print("Please provide at least 2 video files for synchronization.")
        sys.exit(1)

    # Extract metadata for each video
    video_data = {}

    for video in videos:
        creation_time, start_tc, duration, fps = get_metadata(video)
        start_timecode = Timecode('29.97', start_tc) # hardcoded for now, need to extract from video metadata (and round correctly)

        # Extract video name from path after ingress
        video_name = video.replace(ingress, "")

        # check if left or right is part of the video path
        side = ""
        if not "left" in video_name and not "right" in video_name:
            print(f"Skipping {video_name} as it is not clear if it is the right or the left eye. Please include 'left' or 'right' in the path or filename.")
            continue
        else: 
            if "left" in video_name:
                side = "left"
            elif "right" in video_name:
                side = "right"

        print(f"{video_name} --- Created: {creation_time}, Start TC: {start_timecode}, Duration: {duration:.6f} seconds, FPS: {fps}")

        video_data[video] = {
            "creation_time": datetime.fromisoformat(creation_time),
            "start_timecode": start_timecode,
            "fps": fps,
            "side": side
        }

    # match videos into pairs by creation time
    video_pairs = match_videos(video_data)

    print(f"Found {len(video_pairs)} pair(s) of videos for synchronization.")

    # for each pair of videos, clip them
    for video_pair in video_pairs:

        # Determine overlapping timecode interval
        (video1, data1), (video2, data2) = video_pair

        start_tc1 = data1["start_timecode"]
        start_tc2 = data2["start_timecode"]
        start_sec1 = 0.0
        start_sec2 = 0.0

        # Determine the overlapping interval
        if start_tc1 > start_tc2:
            start_difference = start_tc1 - start_tc2
            start_sec2 = start_difference.to_realtime(True)
        else:
            start_difference = start_tc2 - start_tc1
            start_sec1 = start_difference.to_realtime(True)

        # relative start frame
        print(f"Start frame difference: {start_difference.frames} frames, {start_difference.to_realtime(True)} sec, tc: {start_difference}")

        # for metadata
        clip_start_tc = max(start_tc1, start_tc2)

        if organize:
            # Create a folder structure based on creation time
            creation_time = data1["creation_time"]
            folder_name = creation_time.strftime("%Y-%m-%d")
            egress_full = os.path.join(egress, folder_name)
            if not os.path.exists(egress_full):
                os.makedirs(egress_full)

        # Clip and merge videos
        options = "_sync"
        if crop:
            options += "_crop"
        if dewarp:
            options += "_dewarp"
        output_file = os.path.join(egress_full, f"{os.path.splitext(os.path.basename(video1))[0]}_{os.path.splitext(os.path.basename(video2))[0]}{options}.mp4")
        process_videos(video1, video2, start_sec1, start_sec2, output_file, clip_start_tc, crop, dewarp, cuda)

if __name__ == "__main__":
    main()
