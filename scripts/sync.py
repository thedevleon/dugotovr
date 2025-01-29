import subprocess
import os
import sys
import argparse
import glob

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

    # Match videos into pairs
    video_pairs = []
    for i in range(0, len(sorted_videos), 2):
        video1 = sorted_videos[i]
        video2 = sorted_videos[i + 1]
        video_pairs.append((video1, video2))

    return video_pairs

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("ingress", help="the path to ingress from")
    parser.add_argument("egress", help="the path to egress to")
    parser.add_argument("-o", "--organize", help="create a folder structure of year-mm-dd/ at the egress", action="store_true", default=True)
    parser.add_argument("-c", "--crop", help="crop the 8:7 video to 1:1 before merging", action="store_true", default=True)
    parser.parse_args()

    ingress = parser.ingress
    egress = parser.egress
    organize = parser.organize

    # check if the ingress directory exists
    if not os.path.exists(ingress):
        print(f"The ingress directory {ingress} does not exist.")
        sys.exit(1)
    
    # check if the egress directory exists, or create it
    if not os.path.exists(egress):
        os.makedirs(egress)
        print(f"The egress directory {egress} does not exist. Created it.")

    # Get all video files in the ingress directory
    videos = glob.glob(os.path.join(ingress, "*.mp4"))

    if len(videos) < 2:
        print("Please provide at least 2 video files for synchronization.")
        sys.exit(1)

    # Extract metadata for each video
    video_data = {}

    for video in videos:
        creation_time, tc, duration, fps = get_metadata(video)
        start_frames = timecode_to_frames(tc, fps)
        duration_frames = int(duration * fps)
        end_frames = (
            start_frames + duration_frames - 1
        )  # Subtract 1 to get the last frame
        end_tc = frames_to_timecode(end_frames, fps)

        # Extract video name without extension for printing
        video_name = os.path.splitext(video)[0]
        print(f"{video_name} Start: {tc}")
        print(f"{video_name} Duration: {duration:.6f} seconds")
        print(f"{video_name} End: {end_tc}\n")

        video_data[video] = {
            "creation_time": creation_time,
            "start_tc": tc,
            "duration": duration,
            "fps": fps,
            "end_frames": end_frames,
        }

    # match videos into pairs by creation time
    video_pairs = match_videos(video_data)

    # for each pair of videos, clip them
    for video_pair in video_pairs:

        # Determine overlapping timecode interval
        video1, video2 = video_pair

        start1_sec = timecode_to_frames(video1["start_tc"], video1["fps"]) / video1["fps"]
        end1_sec = video1["end_frames"] / video1["fps"]

        start2_sec = timecode_to_frames(video2["start_tc"], video2["fps"]) / video2["fps"]
        end2_sec = video2["end_frames"] / video2["fps"]

        # Determine the overlapping interval
        clip_start_sec = max(start1_sec, start2_sec)
        clip_end_sec = min(end1_sec, end2_sec)

        # Calculate clip duration
        clip_duration_sec = clip_end_sec - clip_start_sec

        if clip_duration_sec <= 0:
            print("No overlapping timecode interval found between the two videos.")
            sys.exit(1)

        # Print overlapping interval details
        overlapping_start_tc = seconds_to_timecode(clip_start_sec, video1["fps"])
        overlapping_end_tc = seconds_to_timecode(clip_end_sec, video2["fps"])

        print(f"Overlapping Interval:")
        print(f"Start: {overlapping_start_tc}")
        print(f"End: {overlapping_end_tc}")
        print(f"Duration: {clip_duration_sec:.6f} seconds\n")

        # Calculate relative start times for each video
        relative_start1 = clip_start_sec - start1_sec
        relative_start2 = clip_start_sec - start2_sec

        # Ensure relative starts are not negative
        relative_start1 = max(relative_start1, 0.0)
        relative_start2 = max(relative_start2, 0.0)

        # TODO
        # build ffmpeg command to clip the videos, crop each view to 1:1 and merge

if __name__ == "__main__":
    main()
