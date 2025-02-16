import argparse
import ffmpeg
import os
import glob
import numpy as np
import cv2
import yaml

from util import *

def extract_frames(video, num_frames):
    out, err = (
        ffmpeg
        .input(video)
        .trim(end_frame=num_frames)
        .filter('crop', 4648, 4648) # crop to the center of the fisheye
        .filter('scale', 4096, 4096) # downscale to 4096x4096
        .output('pipe:', format='rawvideo', pix_fmt='rgb24')
        .run(capture_stdout=True)
    )
    video = (
        np.frombuffer(out, np.uint8)
        .reshape([-1, 4096, 4096, 3])
    )

    return video

# Further improvements:
# allow to seek in the video (i.e. not align on the first frame, but somewhere later in the video)
# fix color mismatch between gplog and normal footage

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ingress", help="the path to ingress from")

    if len(sys.argv) < 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    ingress = args.ingress

    # check if the ingress directory exists
    if not os.path.exists(ingress):
        print(f"The ingress directory {ingress} does not exist.")
        sys.exit(1)

    # Get all video files in the ingress directory
    videos = glob.glob(os.path.join(ingress, "*/*.mp4"))

    if len(videos) < 2:
        print("Please provide at least 2 video files for calibration.")
        sys.exit(1)

    video_pairs = match_videos(videos, ingress)

    print(f"Found {len(video_pairs)} pair(s) of videos for calibration.")

    # keep offset across videos
    x_offset = 0
    y_offset = 0

    for video_pair in video_pairs:
        (video1, data1), (video2, data2) = video_pair

        print(f"Processing video pair: {video1} and {video2}")

        start_tc1 = data1["start_timecode"]
        start_tc2 = data2["start_timecode"]
        start_frame1 = 0
        start_frame2 = 0
        anaglyph = True
        calibration_changed = False

        calibration_file1 = video1.replace(".mp4", ".yaml").replace(".MP4", ".yaml")
        calibration_file2 = video1.replace(".mp4", ".yaml").replace(".MP4", ".yaml")

        # if the calibration files exist, load the calibration data
        if os.path.exists(calibration_file1) and os.path.exists(calibration_file2):
            with open(calibration_file1, "r") as f:
                calibration = yaml.safe_load(f)
                start_frame1 = calibration["start_frame"]
                x_offset = calibration["x_offset"]
                y_offset = calibration["y_offset"]
            with open(calibration_file2, "r") as f:
                calibration = yaml.safe_load(f)
                start_frame2 = calibration["start_frame"]
        else:
            if start_tc1 > start_tc2:
                start_difference = start_tc1 - start_tc2
                start_frame1 = start_difference.frames
            elif start_tc2 > start_tc1:
                start_difference = start_tc2 - start_tc1
                start_frame2 = start_difference.frames
            
        # extract the first 30 frames of each video
        frames1 = extract_frames(video1, 30)
        frames2 = extract_frames(video2, 30)

        print(f"Start frame left: {start_frame1}, right: {start_frame2}, x_offset: {x_offset}, y_offset: {y_offset}")
        
        while True:
            frame1 = np.copy(frames1[start_frame1])
            frame2 = np.copy(frames2[start_frame2])
            
            # offset the frames in x and y and split the difference between the two frames
            frame1 = np.roll(frame1, x_offset, axis=1)
            frame2 = np.roll(frame2, -x_offset, axis=1)
            frame1 = np.roll(frame1, y_offset, axis=0)
            frame2 = np.roll(frame2, -y_offset, axis=0)

            if anaglyph:
                preview = color_anaglyph(frame1, frame2)
            else:
                preview = np.hstack((frame1, frame2))

            cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL) # allows the window to be resized
            cv2.imshow("Calibration", preview)
            key = cv2.waitKey(0)

            if key == ord('q'):
                break
            elif key == ord('w'):
                y_offset -= 1
                calibration_changed = True
            elif key == ord('s'):
                y_offset += 1
                calibration_changed = True
            elif key == ord('a'):
                x_offset -= 1
                calibration_changed = True
            elif key == ord('d'):
                x_offset += 1
                calibration_changed = True
            elif key == ord('j'):
                start_frame1 -= 1
                calibration_changed = True
            elif key == ord('k'):
                start_frame1 += 1
                calibration_changed = True
            elif key == ord('n'):
                start_frame2 -= 1
                calibration_changed = True
            elif key == ord('m'):
                start_frame2 += 1
                calibration_changed = True
            elif key == ord(' '):
                anaglyph = not anaglyph

            start_frame1 = max(0, start_frame1)
            start_frame2 = max(0, start_frame2)

            print(f"Start frame left: {start_frame1}, right: {start_frame2}, x_offset: {x_offset}, y_offset: {y_offset}")

        cv2.destroyAllWindows()

        if calibration_changed:
            print("Saving calibration data...")

            # save the start frame and alignment via a simple text file next to the video file
            with open(f"{os.path.splitext(video1)[0]}.yaml", "w") as f:
                content = {
                    "start_frame": start_frame1,
                    "x_offset": x_offset,
                    "y_offset": y_offset
                }
                yaml.dump(content, f)

            with open(f"{os.path.splitext(video2)[0]}.yaml", "w") as f:
                content = {
                    "start_frame": start_frame2,
                    "x_offset": -x_offset,
                    "y_offset": -y_offset
                }
                yaml.dump(content, f)


if __name__ == "__main__":
    main()
