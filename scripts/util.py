import sys
from timecode import Timecode
from datetime import datetime
from datetime import timedelta
import ffmpeg

def get_metadata(filename):
    """
    Retrieves the creation-time, timecode, duration, and frame rate from the video file.

    :param filename: Path to the video file.
    :return: Tuple containing timecode string, duration in seconds, and frame rate.
    """

    try:
        probe = ffmpeg.probe(filename)
    except ffmpeg.Error as e:
        print(f"Error occurred while probing {filename}: {e.stderr}")
        sys.exit(1)

    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)

    if video_stream is None:
        print(f"No video stream found in {filename}.")
        sys.exit(1) # return none?
    
    creation_time = video_stream.get("tags", {}).get("creation_time", None)
    if creation_time is None:
        print(f"No creation time found for {filename}.")
        sys.exit(1)

    time_code = video_stream.get("tags", {}).get("timecode", None)
    if time_code is None:
        print(f"No timecode found for {filename}.")
        sys.exit(1)

    duration = float(video_stream.get("duration", None))
    if duration is None:
        print(f"No duration found for {filename}.")
        sys.exit(1)

    frame_rate = video_stream.get("r_frame_rate", None)
    if frame_rate is None:
        print(f"No frame rate found for {filename}.")
        sys.exit(1)


    return creation_time, time_code, duration, frame_rate

def match_videos(videos, ingress_path):
    """
    Matches videos into pairs based on creation time.

    :param videos: Dictionary containing videos.
    :return: List of video pairs.
    """

    # Extract metadata for each video
    video_data = {}

    print(f"Found {len(videos)} video(s) in {ingress_path}:")

    for video in videos:
        creation_time, start_tc, duration, frame_rate = get_metadata(video)
        start_timecode = Timecode(frame_rate, start_tc)

        # Extract video name from path after ingress
        video_name = video.replace(ingress_path, "")

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

        print(f"{video_name} --- Created: {creation_time}, Start TC: {start_timecode}, Duration: {duration:.6f} seconds, Framerate: {frame_rate}")

        video_data[video] = {
            "creation_time": datetime.fromisoformat(creation_time),
            "start_timecode": start_timecode,
            "frame_rate": frame_rate,
            "side": side
        }



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
        elif video1[1]["frame_rate"] != video2[1]["frame_rate"]: # Skip videos with different frame rates
            print(
                f"Skipping {video1[0]} and {video2[0]} pair due to different frame rates: {video1[1]['frame_rate']} vs {video2[1]['frame_rate']}"
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