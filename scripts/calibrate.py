import argparse
import ffmpeg
import os
import glob
import numpy as np
import cv2

from util import *

def extract_frames(video, num_frames):
    probe = ffmpeg.probe(video)
    video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    width = int(video_info['width'])
    height = int(video_info['height'])

    out, err = (
        ffmpeg
        .input(video)
        .trim(end_frame=num_frames)
        .output('pipe:', format='rawvideo', pix_fmt='rgb24')
        .run(capture_stdout=True)
    )
    video = (
        np.frombuffer(out, np.uint8)
        .reshape([-1, height, width, 3])
    )

    return video


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

    for video_pair in video_pairs:
        (video1, data1), (video2, data2) = video_pair

        print(f"Processing video pair: {video1} and {video2}")

        start_tc1 = data1["start_timecode"]
        start_tc2 = data2["start_timecode"]

        start_frame1 = 0
        start_frame2 = 0
        x_offset = 0
        y_offset = 0
        anaglyph = True

        if start_tc1 > start_tc2:
            start_difference = start_tc1 - start_tc2
            start_frame1 = start_difference.frames
        elif start_tc2 > start_tc1:
            start_difference = start_tc2 - start_tc1
            start_frame2 = start_difference.frames
            
        # extract the first 30 frames of each video
        frames1 = extract_frames(video1, 30)
        frames2 = extract_frames(video2, 30)
        
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
            elif key == ord('s'):
                y_offset += 1
            elif key == ord('a'):
                x_offset -= 1
            elif key == ord('d'):
                x_offset += 1
            elif key == ord('j'):
                start_frame1 -= 1
            elif key == ord('k'):
                start_frame1 += 1
            elif key == ord('n'):
                start_frame2 -= 1
            elif key == ord('m'):
                start_frame2 += 1
            elif key == ord(' '):
                anaglyph = not anaglyph

            start_frame1 = max(0, start_frame1)
            start_frame2 = max(0, start_frame2)

            print(f"Start frame left: {start_frame1}, right: {start_frame2}, x_offset: {x_offset}, y_offset: {y_offset}")

        # save the start frame and alignment via a simple text file next to the video file
        with open(f"{os.path.splitext(video1)[0]}.txt", "w") as f:
            f.write(f"start_frame: {start_frame1}\n")
            f.write(f"x_offset: {x_offset}\n")
            f.write(f"y_offset: {y_offset}\n")

        with open(f"{os.path.splitext(video2)[0]}.txt", "w") as f:
            f.write(f"start_frame: {start_frame2}\n")
            f.write(f"x_offset: {-x_offset}\n")
            f.write(f"y_offset: {-y_offset}\n")


if __name__ == "__main__":
    main()
