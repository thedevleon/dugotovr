import subprocess
import json
import sys
from timecode import Timecode
from datetime import datetime
from datetime import timedelta

def get_ffprobe_data(filename):
    """
    Uses ffprobe to extract metadata from the video file.

    :param filename: Path to the video file.
    :return: Dictionary containing all metadata.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        filename,
    ]

    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        data = json.loads(result.stdout)
        return data
    except subprocess.CalledProcessError as e:
        print(f"Error running ffprobe on {filename}: {e.stderr}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error parsing ffprobe output for {filename}.")
        sys.exit(1)


def extract_timecode_from_streams(data):
    """
    Extracts timecode from the video stream by prioritizing the video codec type.

    :param data: ffprobe data dictionary.
    :return: Timecode string or None.
    """
    streams = data.get("streams", [])
    for stream in streams:
        if stream.get("codec_type") == "video":
            tags = stream.get("tags", {})
            tc = tags.get("timecode", None)
            if tc:
                return tc
    return None


def extract_timecode(data):
    """
    Extracts timecode from ffprobe data by searching the video stream first,
    then other streams if necessary.

    :param data: ffprobe data dictionary.
    :return: Timecode string or None.
    """
    # Attempt to extract from video stream
    tc = extract_timecode_from_streams(data)
    if tc:
        return tc

    # Fallback: Search all streams
    for stream in data.get("streams", []):
        tags = stream.get("tags", {})
        for key, value in tags.items():
            if "timecode" in key.lower():
                return value

    # Fallback: Search format tags
    format_tags = data.get("format", {}).get("tags", {})
    for key, value in format_tags.items():
        if "timecode" in key.lower():
            return value

    return None

def extract_creation_time_from_streams(data):
    """
    Extracts creation time from the video stream by prioritizing the video codec type.

    :param data: ffprobe data dictionary.
    :return: creation time string or None.
    """
    streams = data.get("streams", [])
    for stream in streams:
        if stream.get("codec_type") == "video":
            tags = stream.get("tags", {})
            creation_time = tags.get("creation_time", None)
            if creation_time:
                return creation_time
    return None


def extract_creation_time(data):
    """
    Extracts creation time from ffprobe data by searching the video stream first,
    then other streams if necessary.

    :param data: ffprobe data dictionary.
    :return: creation time string or None.
    """
    # Attempt to extract from video stream
    creation_time = extract_creation_time_from_streams(data)
    if creation_time:
        return creation_time

    # Fallback: Search all streams
    for stream in data.get("streams", []):
        tags = stream.get("tags", {})
        for key, value in tags.items():
            if "creation_time" in key.lower():
                return value

    # Fallback: Search format tags
    format_tags = data.get("format", {}).get("tags", {})
    for key, value in format_tags.items():
        if "creation_time" in key.lower():
            return value

    return None


def get_frame_rate(data):
    """
    Retrieves the frame rate from the video stream.

    :param data: ffprobe data dictionary.
    :return: Frame rate as a float.
    """
    streams = data.get("streams", [])
    for stream in streams:
        if stream.get("codec_type") == "video":
            r_frame_rate = stream.get("r_frame_rate", "30/1")
            try:
                num, den = map(int, r_frame_rate.split("/"))
                fps = num / den
                return '{:.2f}'.format(fps)
            except:
                print(
                    f"Invalid r_frame_rate format: {r_frame_rate}. Defaulting to 29.97 fps."
                )
                return 29.97
    print("No video stream found to determine frame rate. Defaulting to 29.97 fps.")
    return 29.97

def get_metadata(filename):
    """
    Retrieves the creation-time, timecode, duration, and frame rate from the video file.

    :param filename: Path to the video file.
    :return: Tuple containing timecode string, duration in seconds, and frame rate.
    """
    data = get_ffprobe_data(filename)
    creation_time = extract_creation_time(data)
    tc = extract_timecode(data)
    if tc is None:
        print(f"No timecode found for {filename}.")
        sys.exit(1)

    # Get duration
    duration = data.get("format", {}).get("duration", None)
    if duration is None:
        print(f"No duration found for {filename}.")
        sys.exit(1)

    try:
        duration = float(duration)
    except ValueError:
        print(f"Invalid duration value for {filename}: {duration}")
        sys.exit(1)

    # Get frame rate
    fps = get_frame_rate(data)

    return creation_time, tc, duration, fps

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
        creation_time, start_tc, duration, fps = get_metadata(video)
        start_timecode = Timecode(fps, start_tc)

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

        print(f"{video_name} --- Created: {creation_time}, Start TC: {start_timecode}, Duration: {duration:.6f} seconds, FPS: {fps}")

        video_data[video] = {
            "creation_time": datetime.fromisoformat(creation_time),
            "start_timecode": start_timecode,
            "fps": fps,
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