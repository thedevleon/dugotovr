import subprocess
import json
import sys

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
                return num / den
            except:
                print(
                    f"Invalid r_frame_rate format: {r_frame_rate}. Defaulting to 30 fps."
                )
                return 30.0
    print("No video stream found to determine frame rate. Defaulting to 30 fps.")
    return 30.0


def timecode_to_frames(tc, fps):
    """
    Converts a timecode string to total frames.

    :param tc: Timecode string in format "HH:MM:SS;FF" or "HH:MM:SS.FF"
    :param fps: Frames per second as a float.
    :return: Total number of frames as integer.
    """
    try:
        if ";" in tc:
            time_part, frame_part = tc.strip().split(";")
        elif "." in tc:
            time_part, frame_part = tc.strip().split(".")
        else:
            print(f"Unsupported timecode format: {tc}")
            sys.exit(1)

        h, m, s = map(int, time_part.split(":"))
        f = int(frame_part)
        total_seconds = h * 3600 + m * 60 + s
        total_frames = int(total_seconds * fps) + f
        return total_frames
    except ValueError:
        print(f"Invalid timecode format: {tc}")
        sys.exit(1)


def frames_to_timecode(total_frames, fps):
    """
    Converts total frames back to a timecode string.

    :param total_frames: Total number of frames as integer.
    :param fps: Frames per second as a float.
    :return: Timecode string in format "HH:MM:SS;FF"
    """
    h = int(total_frames // (fps * 3600))
    remaining = total_frames - (h * fps * 3600)
    m = int(remaining // (fps * 60))
    remaining = remaining - (m * fps * 60)
    s = int(remaining // fps)
    f = int(remaining - (s * fps)) + 1 # needed?

    # Handle cases where frame count exceeds fps
    if f >= int(fps):
        f = 0
        s += 1
        if s >= 60:
            s = 0
            m += 1
            if m >= 60:
                m = 0
                h += 1

    return f"{h:02}:{m:02}:{s:02};{f:02}"


def seconds_to_timecode(seconds, fps):
    """
    Converts total seconds to a timecode string in format "HH:MM:SS;FF"

    :param seconds: Total seconds as a float.
    :param fps: Frames per second as a float.
    :return: Timecode string in format "HH:MM:SS;FF"
    """
    h = int(seconds // 3600)
    seconds %= 3600
    m = int(seconds // 60)
    seconds %= 60
    s = int(seconds)
    f = int((seconds - s) * fps)

    # Handle cases where frame count exceeds fps
    if f >= int(fps):
        f = 0
        s += 1
        if s >= 60:
            s = 0
            m += 1
            if m >= 60:
                m = 0
                h += 1

    return f"{h:02}:{m:02}:{s:02};{f:02}"


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