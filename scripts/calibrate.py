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
# add support for rotation

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ingress", help="the path to ingress from")
    parser.add_argument("-s", "--skip", help="skip already calibrated files", action="store_true")

    if len(sys.argv) < 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    ingress = args.ingress
    skip = args.skip

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
    rotation_global = 0.0 # to correct horizon on both
    rotation_local = 0.0 # to correct rotation against each other

    frames_to_extract = 30 # 30 should be enough

    for video_pair in video_pairs:
        (video1, data1), (video2, data2) = video_pair

        print(f"Processing video pair: {video1} and {video2}")

        start_tc1 = data1["start_timecode"]
        start_tc2 = data2["start_timecode"]
        seek = 0
        start_frame1 = 0
        start_frame1_orig = 0
        start_frame2 = 0
        start_frame2_orig = 0
        anaglyph = True
        lines = True
        calibration_changed = False

        calibration_file1 = video1.replace(".mp4", ".yaml").replace(".MP4", ".yaml")
        calibration_file2 = video2.replace(".mp4", ".yaml").replace(".MP4", ".yaml")

        # if the calibration files exist, load the calibration data
        if os.path.exists(calibration_file1) and os.path.exists(calibration_file2):
            with open(calibration_file1, "r") as f:
                calibration = yaml.safe_load(f)
                start_frame1 = calibration["start_frame"]
                x_offset = calibration["x_offset"]
                y_offset = calibration["y_offset"]
                rotation_global = calibration["rotation_global"] if "rotation_global" in calibration else rotation_global # backwards compatibility
                rotation_local = calibration["rotation_local"] if "rotation_local" in calibration else rotation_local # backwards compatibility
            with open(calibration_file2, "r") as f:
                calibration = yaml.safe_load(f)
                start_frame2 = calibration["start_frame"]

            print(start_frame1, start_frame2)

            if skip:
                print("Skipping calibration for this video pair.")
                continue
        else:
            calibration_changed = True # calibration data is missing
            if start_tc1 > start_tc2:
                start_difference = start_tc1 - start_tc2
                start_frame2 = start_difference.frames
                start_frame2_orig = start_difference.frames
            elif start_tc2 > start_tc1:
                start_difference = start_tc2 - start_tc1
                start_frame1 = start_difference.frames
                start_frame1_orig = start_difference.frames
            
        # extract the first 30 frames of each video
        frames1 = extract_frames(video1, frames_to_extract+1)
        frames2 = extract_frames(video2, frames_to_extract+1)
        
        while True:
            print(f"Seek: {seek}, start frame left: {start_frame1}, start frame right: {start_frame2}, x_offset: {x_offset}, y_offset: {y_offset}, rotation (local): {rotation_local}, rotation (global): {rotation_global}")

            frame1 = np.copy(frames1[seek + start_frame1])
            frame2 = np.copy(frames2[seek + start_frame2])
            
            # offset the frames in x and y and split the difference between the two frames
            frame1 = np.roll(frame1, x_offset, axis=1)
            frame2 = np.roll(frame2, -x_offset, axis=1)
            frame1 = np.roll(frame1, y_offset, axis=0)
            frame2 = np.roll(frame2, -y_offset, axis=0)

            # rotate the frames
            frame1 = cv2.warpAffine(frame1, cv2.getRotationMatrix2D((2048, 2048), rotation_global + rotation_local, 1), (4096, 4096))
            frame2 = cv2.warpAffine(frame2, cv2.getRotationMatrix2D((2048, 2048), rotation_global - rotation_local, 1), (4096, 4096))

            # add a horizontal grid to the frames
            if lines:
                thickness = 6
                color = (255, 255, 255)
                cv2.line(frame1, (0, 2048), (4096, 2048), color, thickness)
                cv2.line(frame2, (0, 2048), (4096, 2048), color, thickness)
                cv2.line(frame1, (0, 1024), (4096, 1024), color, thickness)
                cv2.line(frame2, (0, 1024), (4096, 1024), color, thickness)
                cv2.line(frame1, (0, 3072), (4096, 3072), color, thickness)
                cv2.line(frame2, (0, 3072), (4096, 3072), color, thickness)

            # fix color issues
            frame1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2RGB)
            frame2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2RGB)

            if anaglyph:
                preview = color_anaglyph(frame1, frame2)
            else:
                preview = np.hstack((frame1, frame2))

            # add text for debugging to frame1
            # top left: seek, left start, right start
            # top right: x_offset, y_offset
            # top bottom: legend for controls
            font_scale = 2
            font_thickness = 3
            color = (255, 255, 255)
            top_left_text_1 = f"Seek: {seek}, Left: {start_frame1}, Right: {start_frame2}"
            top_left_text_2 = f"X: {x_offset}, Y: {y_offset}, Rot (l): {rotation_local:.2f}, Rot (g): {rotation_global:.2f}"
            bottom_left_text_1 = "WASD: X/Y Offset, N/M: Left, J/K: Right, I/O: Seek, ,/.: Rot (l), -/+: Rot (g), R: Reset, Space: Anaglyph, Q: Quit, E: Next"

            # get text size with cv2.getTextSize
            (_, top_left_text_1_height), _ = cv2.getTextSize(top_left_text_1, cv2.FONT_HERSHEY_DUPLEX, font_scale, font_thickness)
            (_, top_left_text_2_height), _ = cv2.getTextSize(top_left_text_2, cv2.FONT_HERSHEY_DUPLEX, font_scale, font_thickness)
            cv2.putText(preview, top_left_text_1, (10, 10 + top_left_text_1_height), cv2.FONT_HERSHEY_DUPLEX, font_scale, color, font_thickness, cv2.LINE_AA)
            cv2.putText(preview, top_left_text_2, (10, 10 + top_left_text_1_height + 10 + top_left_text_2_height), cv2.FONT_HERSHEY_DUPLEX, font_scale, color, font_thickness, cv2.LINE_AA)
            cv2.putText(preview, bottom_left_text_1, (10, preview.shape[0] - 10), cv2.FONT_HERSHEY_DUPLEX, font_scale, color, font_thickness, cv2.LINE_AA)

            cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL) # allows the window to be resized
            cv2.imshow("Calibration", preview)
            key = cv2.waitKey(0)

            if key == ord('q'):
                return
            elif key == ord('e'):
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
            elif key == ord('n'):
                start_frame1 -= 1
                calibration_changed = True
            elif key == ord('m'):
                start_frame1 += 1
                calibration_changed = True
            elif key == ord('j'):
                start_frame2 -= 1
                calibration_changed = True
            elif key == ord('k'):
                start_frame2 += 1
                calibration_changed = True
            elif key == ord('-'):
                rotation_global += 0.1
                calibration_changed = True
            elif key == ord('='):
                rotation_global -= 0.1
                calibration_changed = True
            elif key == ord(','):
                rotation_local -= 0.1
                calibration_changed = True
            elif key == ord('.'):
                rotation_local += 0.1
                calibration_changed = True
            elif key == ord(' '):
                anaglyph = not anaglyph
            elif key == ord('h'):
                lines = not lines
            elif key == ord('i'):
                seek -= 1
            elif key == ord('o'):
                seek += 1
            elif key == ord('r'):
                seek = 0
                x_offset = 0
                y_offset = 0
                start_frame1 = start_frame1_orig
                start_frame2 = start_frame2_orig
                calibration_changed = True

            start_frame1 = min(max(0, start_frame1), frames_to_extract)
            start_frame2 = min(max(0, start_frame2), frames_to_extract)
            seek = min(max(0, seek), frames_to_extract) # clamp between 0 and frames_to_extract
            seek = min(min(frames_to_extract - start_frame1, frames_to_extract - start_frame2), seek) # make sure we don't seek too far
            seek = max(0, seek) # and make sure we don't seek into negative frames
        cv2.destroyAllWindows()

        if calibration_changed:
            print("Saving calibration data...")

            # save the start frame and alignment via a simple text file next to the video file
            with open(f"{os.path.splitext(video1)[0]}.yaml", "w") as f:
                content = {
                    "start_frame": start_frame1,
                    "x_offset": x_offset,
                    "y_offset": y_offset,
                    "rotation_global": rotation_global,
                    "rotation_local": rotation_local
                }
                yaml.dump(content, f)

            with open(f"{os.path.splitext(video2)[0]}.yaml", "w") as f:
                content = {
                    "start_frame": start_frame2,
                    "x_offset": -x_offset,
                    "y_offset": -y_offset,
                    "rotation_global": rotation_global,
                    "rotation_local": -rotation_local
                }
                yaml.dump(content, f)


if __name__ == "__main__":
    main()
