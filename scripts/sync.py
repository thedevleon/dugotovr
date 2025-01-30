import subprocess
import os
import sys
import argparse
import glob
from datetime import datetime
from datetime import timedelta

from util import *


# def clip_video(input_file, output_file, start_time, duration, new_timecode):
#     """
#     Clips a video using FFmpeg and resets the timecode while preserving original codecs.

#     :param input_file: Path to the input video file.
#     :param output_file: Path to the output (clipped) video file.
#     :param start_time: Start time in seconds.
#     :param duration: Duration in seconds.
#     :param new_timecode: New timecode to set (format "HH:MM:SS;FF").
#     """
#     cmd = [
#         "ffmpeg",
#         "-ss",
#         f"{start_time:.6f}",
#         "-t",
#         f"{duration:.6f}",
#         "-i",
#         input_file,
#         "-c",
#         "copy",  # Copy codecs
#         "-metadata",
#         f"timecode={new_timecode}",  # Set new timecode
#         output_file,
#     ]

#     try:
#         print(f"Clipping {input_file} -> {output_file}")
#         subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
#         print(f"Successfully clipped {output_file}\n")
#     except subprocess.CalledProcessError as e:
#         print(f"Error clipping {input_file}: {e.stderr}")
#         sys.exit(1)

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
            video_pairs.append((video1, video2))

    return video_pairs


def clip_and_merge_videos(video1, video2, start_sec1, start_sec2, duration_sec, fps, output_file, crop=False):
    # arguments for ffmpeg
    # -ss: start time (in seconds), not timecode
    # -t: duration (in seconds), not timecode
    
    print(video1, video2, start_sec1, start_sec2, duration_sec, fps, output_file, crop)

    pass

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("ingress", help="the path to ingress from")
    parser.add_argument("egress", help="the path to egress to")
    parser.add_argument("-o", "--organize", help="create a folder structure of year-mm-dd/ at the egress", action="store_true", default=True)
    parser.add_argument("-c", "--crop", help="crop the 8:7 video to 1:1 before merging", action="store_true", default=True)

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    ingress = args.ingress
    egress = args.egress
    organize = args.organize

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
        start_frame = timecode_to_frames(start_tc, fps)
        duration_frames = int(duration * fps)
        end_frame = (
            start_frame + duration_frames - 1
        )  # Subtract 1 to get the last frame
        end_tc = frames_to_timecode(end_frame, fps)

        # Extract video name from path after ingress
        video_name = video.replace(ingress, "")

        print(f"{video_name} --- Created: {creation_time}, Start TC: {start_tc}, End TC: {end_tc} Duration: {duration:.6f} seconds, FPS: {fps}")

        video_data[video] = {
            "creation_time": datetime.fromisoformat(creation_time),
            "start_tc": start_tc,
            "end_tc": end_tc,
            "duration": duration,
            "fps": fps,
            "start_frame": start_frame,
            "end_frame": end_frame,
        }

    # match videos into pairs by creation time
    video_pairs = match_videos(video_data)

    print(f"Found {len(video_pairs)} pair(s) of videos for synchronization.")

    # for each pair of videos, clip them
    for video_pair in video_pairs:

        # Determine overlapping timecode interval
        (video1, data1), (video2, data2) = video_pair
        fps = data1["fps"]

        # Determine the overlapping interval
        clip_start_frame = max(data1["start_frame"], data2["start_frame"])
        clip_end_frame = min(data1["end_frame"], data1["end_frame"])
        clip_duration_frames = clip_end_frame - clip_start_frame
        clip_duration_seconds = clip_duration_frames / fps

        # relative start frame
        start_frame1 = clip_start_frame - data1["start_frame"]
        start_frame2 = clip_start_frame - data2["start_frame"]
        start_sec1 = start_frame1 / fps
        start_sec2 = start_frame2 / fps

        # Clip and merge videos
        output_file = os.path.join(egress, f"{os.path.splitext(os.path.basename(video1))[0]}_{os.path.splitext(os.path.basename(video2))[0]}.mp4")
        clip_and_merge_videos(video1, video2, start_sec1, start_sec2, clip_duration_seconds, fps, output_file, crop=args.crop)

if __name__ == "__main__":
    main()
