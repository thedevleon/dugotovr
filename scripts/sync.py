import subprocess
import os
import sys
import argparse
import glob
import yaml
import math

from util import *

def process_videos(video1, video2, calibration, output_file, tc, dewarp, cuda, preview):
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

    # gopro file format wierdness
    # gp-log: yuvj420p
    # normal: yuv420p10le

    # rotation 
    v1_rotate = f"rotate={calibration['rotate_global1'] + calibration['rotate_local1']}*(PI/180):ow=4096:oh=4096"
    v2_rotate = f"rotate={calibration['rotate_global2'] + calibration['rotate_local2']}*(PI/180):ow=4096:oh=4096"

    # calculate parameters for crop and pad filters for x/y stereo alignment
    # crop: w:h:x:y
    # pad: w:h:x:y
    v1_crop = f"crop={4096-abs(calibration['offset1_x'])}:{4096-abs(calibration['offset1_y'])}:{abs(calibration['offset1_x']) if calibration['offset1_x'] < 0 else 0}:{abs(calibration['offset1_y']) if calibration['offset1_y'] < 0 else 0}"
    v2_crop = f"crop={4096-abs(calibration['offset2_x'])}:{4096-abs(calibration['offset2_y'])}:{abs(calibration['offset2_x']) if calibration['offset2_x'] < 0 else 0}:{abs(calibration['offset2_y']) if calibration['offset2_y'] < 0 else 0}"
    v1_pad = f"pad=4096:4096:{abs(calibration['offset1_x']) if calibration['offset1_x'] > 0 else 0}:{abs(calibration['offset1_y']) if calibration['offset1_y'] > 0 else 0}"
    v2_pad = f"pad=4096:4096:{abs(calibration['offset2_x']) if calibration['offset2_x'] > 0 else 0}:{abs(calibration['offset2_y']) if calibration['offset2_y'] > 0 else 0}"

    if cuda:

        # Unfortunate limitations of ffmpeg with CUDA acceleration
        # overlay_cuda does not support 10-bit video (p010le), so we can't use it and need to do hstack on the CPU instead, uploading and downloading the frames to and from the GPU in between 
        # hevc_nvenc only supports up to 8K resolution (8192), so we need to crop the video to 1:1 before merging
        # hwdownload does not support yuvj420p, so we need to force format=p010le at the scale_cuda filter (GPLog is apparently yuvj420p)
        # v360 only supports yuv420p10le and yuvj420p
        # yuv420p10le == p010le (apparently, see https://www.reddit.com/r/ffmpeg/comments/c1im2i/encode_4k_hdr_pixel_format/)

        filter_complex = ""
        if dewarp: # around 8.5 FPS
            filter_complex = f"[0:v] scale_cuda=4096:4096:format=p010le [l]; [1:v] scale_cuda=4096:4096:format=p010le [r]; [l] hwdownload,format=p010le [ls]; [r] hwdownload,format=p010le [rs]; [ls] format=p010le,format=yuv420p10le [lss]; [rs] format=p010le,format=yuv420p10le [rss]; [lss] {v1_rotate} [lr]; [rss] {v2_rotate} [rr]; [lr] {v1_crop},{v1_pad} [lc]; [rr] {v2_crop},{v2_pad} [rc]; [lc][rc] hstack=inputs=2 [out]; [out] v360=fisheye:hequirect:ih_fov=177:iv_fov=177:in_stereo=sbs:out_stereo=sbs [dewarp]; [dewarp] hwupload_cuda" 
        if not dewarp: # around 23 FPS
            filter_complex = f"[0:v] scale_cuda=4096:4096:format=p010le [l]; [1:v] scale_cuda=4096:4096:format=p010le [r]; [l] hwdownload,format=p010le [ls]; [r] hwdownload,format=p010le[rs]; [ls] {v1_rotate} [lr]; [rs] {v2_rotate} [rr]; [lr] {v1_crop},{v1_pad} [lc]; [rr] {v2_crop},{v2_pad} [rc]; [lc][rc] hstack=inputs=2 [out]; [out] hwupload_cuda"

        cmd = [
            "ffmpeg",
            "-hwaccel",
            "cuda",
            "-hwaccel_output_format",
            "cuda",
            "-c:v",
            "hevc_cuvid",
            "-crop",
            "0x0x332x332",
            "-ss",
            f"{calibration["start_sec1"]:.6f}",
            "-i",
            video1,
            "-hwaccel",
            "cuda",
            "-hwaccel_output_format",
            "cuda",
            "-c:v",
            "hevc_cuvid",
            "-crop",
            "0x0x332x332",
            "-ss",
            f"{calibration["start_sec2"]:.6f}",
            "-i",
            video2,
            "-shortest", # stop encoding when the shortest input ends
            "-t" if preview else None,
            "15" if preview else None,
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
        if dewarp:
            filter_complex = f"[0:v] crop=4648:4648,scale=4096:4096 [l]; [1:v] crop=4648:4648,scale=4096:4096 [r]; [l] {v1_rotate} [lr]; [r] {v2_rotate} [rr]; [lr] {v1_crop},{v1_pad} [ls]; [rr] {v2_crop},{v2_pad} [rs]; [ls][rs] hstack=inputs=2 [out]; [out] v360=fisheye:hequirect:ih_fov=177:iv_fov=177:in_stereo=sbs:out_stereo=sbs"
        if not dewarp:
            filter_complex = f"[0:v] crop=4648:4648,scale=4096:4096 [l]; [1:v] crop=4648:4648,scale=4096:4096 [r]; [l] {v1_rotate} [lr]; [r] {v2_rotate} [rr]; [lr] {v1_crop},{v1_pad} [ls]; [rr] {v2_crop},{v2_pad} [rs]; [ls][rs] hstack=inputs=2 [out]"

        cmd = [
            "ffmpeg",
            "-ss",
            f"{calibration["start_sec1"]:.6f}",
            "-i",
            video1,
            "-ss",
            f"{calibration["start_sec2"]:.6f}",
            "-i",
            video2,
            "-shortest", # stop encoding when the shortest input ends
            "-t" if preview else None,
            "15" if preview else None,
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

        # remove all None values from the list
    cmd = list(filter(None, cmd))

    print(" ".join(cmd))

    try:
        print(f"Processing {video1} and {video2} -> {output_file}")
        subprocess.run(cmd, check=True)
        print(f"Successfully processed {output_file}\n")
    except subprocess.CalledProcessError as e:
        print(f"Error processing {video1} and {video2}: {e.stderr}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ingress", help="the path to ingress from")
    parser.add_argument("egress", help="the path to egress to")
    parser.add_argument("-o", "--organize", help="create a folder structure of year-mm-dd/ at the egress", action="store_true", default=True)
    parser.add_argument("-d", "--dewarp", help="dewarp the fisheye video to VR180", action="store_true", default=False)
    parser.add_argument("-p", "--preview", help="generate only a preview (15s)", action="store_true", default=False)
    parser.add_argument("--cuda", help="use CUDA accelerated operations", action="store_true", default=True)
    parser.add_argument('--no-cuda', dest='cuda', action='store_false')

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    ingress = args.ingress
    egress = args.egress
    organize = args.organize
    dewarp = args.dewarp
    cuda = args.cuda
    preview = args.preview

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

    video_pairs = match_videos(videos, ingress)

    print(f"Found {len(video_pairs)} pair(s) of videos for synchronization.")

    # for each pair of videos, clip them
    for video_pair in video_pairs:

        # Determine overlapping timecode interval
        (video1, data1), (video2, data2) = video_pair

        print(f"Processing video pair: {video1} and {video2}")

        start_tc1 = data1["start_timecode"]
        start_tc2 = data2["start_timecode"]
        calibration = {
            "start_frame1": 0,
            "start_sec1": 0.0,
            "start_frame2": 0,
            "start_sec2": 0.0,
            "offset1_x": 0.0,
            "offset1_y": 0.0,
            "offset2_x": 0.0,
            "offset2_y": 0.0,
            "rotate_global1": 0.0,
            "rotate_global2": 0.0,
            "rotate_local1": 0.0,
            "rotate_local2": 0.0
        }

        # for metadata only
        clip_start_tc = max(start_tc1, start_tc2)

        calibration_file1 = video1.replace(".mp4", ".yaml").replace(".MP4", ".yaml")
        calibration_file2 = video2.replace(".mp4", ".yaml").replace(".MP4", ".yaml")

        if os.path.exists(calibration_file1) and os.path.exists(calibration_file2):
            with open(calibration_file1, "r") as f:
                calibration1 = yaml.safe_load(f)
                calibration["start_frame1"] = calibration1["start_frame"]
                calibration["start_sec1"] = Timecode('29.97', frames=calibration["start_frame1"]+1).to_realtime(True) # will be obsolete with ffmpeg bindings
                calibration["offset1_x"] = calibration1["x_offset"]
                calibration["offset1_y"] = calibration1["y_offset"]
                calibration["rotate_global1"] = calibration1["rotation_global"] if "rotation_global" in calibration1 else 0.0 # backwards compatibility
                calibration["rotate_local1"] = calibration1["rotation_local"] if "rotation_local" in calibration1 else 0.0 # backwards compatibility
            with open(calibration_file2, "r") as f:
                calibration2 = yaml.safe_load(f)
                calibration["start_frame2"] = calibration2["start_frame"]
                calibration["start_sec2"] = Timecode('29.97', frames=calibration["start_frame2"]+1).to_realtime(True) # will be obsolete with ffmpeg bindings
                calibration["offset2_x"] = calibration2["x_offset"]
                calibration["offset2_y"] = calibration2["y_offset"]
                calibration["rotate_global2"] = calibration2["rotation_global"] if "rotation_global" in calibration2 else 0.0 # backwards compatibility
                calibration["rotate_local2"] = calibration2["rotation_local"] if "rotation_local" in calibration2 else 0.0 # backwards compatibility

            print(f"Start times from calibration files: left: {calibration["start_frame1"]} - {calibration["start_sec1"]:.6f} and right: {calibration["start_frame1"]} - {calibration["start_sec2"]:.6f}")

        else:
            # Determine the overlapping interval
            if start_tc1 > start_tc2:
                start_difference = start_tc1 - start_tc2
                calibration["start_sec2"] = start_difference.to_realtime(True)
            elif start_tc2 > start_tc1:
                start_difference = start_tc2 - start_tc1
                calibration["start_sec1"] = start_difference.to_realtime(True)
            else:
                start_difference = Timecode('29.97', 0)

            if start_difference.frames > 1:
                # relative start frame
                print(f"Start frame difference: {start_difference.frames} frames, {start_difference.to_realtime(True)} sec, tc: {start_difference}")
            else:
                print(f"⭐ You got a perfect match! tc: {clip_start_tc} ⭐")

        if organize:
            # Create a folder structure based on creation time
            creation_time = data1["creation_time"]
            folder_name = creation_time.strftime("%Y-%m-%d")
            egress_full = os.path.join(egress, folder_name)
            if not os.path.exists(egress_full):
                os.makedirs(egress_full)

        # Clip and merge videos
        options = "_sync_crop"
        if dewarp:
            options += "_dewarp"
        if preview:
            options += "_preview"
        output_file = os.path.join(egress_full, f"{os.path.splitext(os.path.basename(video1))[0]}_{os.path.splitext(os.path.basename(video2))[0]}{options}.mp4")
        process_videos(video1, video2, calibration, output_file, clip_start_tc, dewarp, cuda, preview)

if __name__ == "__main__":
    main()
