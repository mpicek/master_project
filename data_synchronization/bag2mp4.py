import sys
sys.path.append('/repo/data_synchronization')
import ffmpegio
import pyrealsense2 as rs
import numpy as np
import cv2
import matplotlib.pyplot as plt
import os
import subprocess
import shutil
from mediapipe_utils import *
from synchronization_utils import *
from tqdm import tqdm
import argparse
import pandas as pd

def create_videos_from_bag(path_bag, output_folder):
    """
    Extracts a vector representing face movement over time from a realsense .bag file.

    This function processes a the .bag file specified by `path_bag` to detect and track
    a bellow nose to forehead vector using a Mediapipe face model.

    Parameters:
    - path_bag (str): Path to the .bag file containing the realsense data.
    - mediapipe_face_model_file (str): Path to the Mediapipe face model file for face detection.

    Returns:
    - numpy.ndarray: An array of shape (frames, 3)
      Each row contains the x, y, z vector direction relative to another facial point.

    Notes:
    - The function assumes a video resolution of 640x480.
    - RealSense SDK is used for video processing, and playback is adjusted to process frames
      as needed, avoiding real-time constraints.
    - Frames where the face is not detected are handled by repeating the last valid detection.
    - The function visualizes face landmarks and their movements in real-time during processing.
    - Press 'q' to quit the visualization and processing early.
    - The function smooths the movement data for visualization purposes.

    Raises:
    - Exception: If there are issues initializing the video pipeline or processing frames.
    """

    img_height = 480
    img_width = 640

    pipeline = rs.pipeline()
    config = rs.config()
    rs.config.enable_device_from_file(config, path_bag)

    config.enable_stream(rs.stream.depth, img_width, img_height, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, img_width, img_height, rs.format.bgr8, 30)

    profile = pipeline.start(config)
    playback = profile.get_device().as_playback()
    
    # we want to set_real_time to False, so that we can process the frames as slowly as necessary.
    # However, there are errors reading it at the beginning and at the end (hopefully not in the middle)
    # when we set it to False right at the beginning. Therefore, we set it to True at the beginning 
    # and then to False after the first frame is read. The end is handled differently - with reading the frames
    # up to the duration of the video - 1s (to be sure that we don't miss the last frame)
    playback.set_real_time(True)

    first_frame = True
    prev_ts = -1
    max_frame_nb = 0
    frame_nb = -1

    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1) 
    ts = 0
    time_series = []
    frames_list = []
    duration = playback.get_duration().total_seconds() * 1000
    print(f"Overall video duration: {playback.get_duration()}")
    video_counter = 0
    failed = False
    # playback.seek(datetime.timedelta(seconds=73*4))
    try:
        while True:
            try:
                frames = pipeline.wait_for_frames()
            except Exception as e:
                print("READING ERROR")
                duration = prev_ts # use previous timestamp as the current one can be corrupt
                print(f"Duration after reading error: {duration // (1000*60)}:{(duration // 1000) % 60}:{(duration % 1000) // 10}")
                failed = str(e)
                break


            depth_frame = frames.get_depth_frame()
            color_frame = frames.get_color_frame()

            playback.set_real_time(False)

            # skipped frame by RealSense
            if not depth_frame or not color_frame:
                if len(frames_list) > 0:
                    frames_list.append(frames_list[-1])
                else:
                    # the detection will not work, which is ok, we filter it with quality
                    frames_list.append(np.zeros((480, 640, 3), dtype=np.uint8))
                continue

            last_frame_nb = frame_nb
            frame_nb = color_frame.get_frame_number()

            # finish of the file (no more new frames)
            if frame_nb < max_frame_nb:
                break

            max_frame_nb = frame_nb

            ts = frames.get_timestamp()


            depth_image_rs = np.asanyarray(depth_frame.get_data())
            color_image_rs = np.asanyarray(color_frame.get_data()) # returns RGB!

            frames_list.append(cv2.cvtColor(color_image_rs, cv2.COLOR_BGR2RGB))

            if first_frame: 
                t0 = ts
                first_frame = False
            
            # the video is at the end (without the last second) so we kill the reading
            # (there was an error with the last frame, this handles it)
            if ts - t0 + 1000 > duration:
                break

            if prev_ts >= int(ts-t0):
                # doubled frame or some other error in ordering (we don't include the frame
                # as we don't want it multiple times)
                if len(frames_list) > 0:
                    frames_list.append(frames_list[-1])
                else:
                    # the detection will not work, which is ok, we filter it with quality
                    frames_list.append(np.zeros((480, 640, 3), dtype=np.uint8))
                continue

            
            prev_prev_ts = prev_ts
            prev_ts = int(ts-t0)

            if prev_ts - prev_prev_ts > 2*int(1000/30) - 10:
                num_of_skipped_frames = (prev_ts - prev_prev_ts) // int(1000/30)
                if len(frames_list) > 0:
                    for i in range(num_of_skipped_frames):
                        frames_list.append(frames_list[-1])
                else:
                    for i in range(num_of_skipped_frames):
                        frames_list.append(np.zeros((480, 640, 3), dtype=np.uint8))

            time_series.append([prev_ts])

            ch = cv2.waitKey(1)
            if ch==113: #q pressed
                failed = "Keyboard Interrupt"
                break


            if len(time_series) % (30*30) == 0:
                formatted_number = '{:04d}'.format(video_counter)
                frames_list = np.stack(frames_list)
                ffmpegio.video.write(os.path.join(output_folder, formatted_number + '.mp4'), 30, frames_list, show_log=True, loglevel="warning")
                print(f"{len(time_series) / (30*30) / 2} minutes processed")
                frames_list = []
                video_counter += 1

            t = ts - t0
    except Exception as e:
        failed = str(e)
        duration = prev_ts

    finally:
        if len(frames_list) > 0:
            frames_list = np.stack(frames_list)
            non_zero_index = np.where((frames_list != np.zeros((480, 640, 3))).any(axis=1))[0][0]
            frames_list[:non_zero_index] = frames_list[non_zero_index]
            formatted_number = '{:04d}'.format(video_counter)
            ffmpegio.video.write(os.path.join(output_folder, formatted_number + '.mp4'), 30, frames_list, show_log=True, loglevel="warning")
            print(f"{len(time_series) / (30*30) / 2} minutes processed")
        pipeline.stop()
        cv2.destroyAllWindows()
    
    return prev_ts / 1000, failed, len(time_series)


def bag2mp4(path_bag, output_folder):

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    tmp_folder = os.path.join(output_folder, 'tmp')
    if os.path.exists(tmp_folder):
        shutil.rmtree(tmp_folder)
    os.makedirs(tmp_folder)

    duration, failed, num_frames = create_videos_from_bag(path_bag, tmp_folder)
    np.save(os.path.join(output_folder, os.path.basename(path_bag)[:-4] + '_duration.npy'), duration)

    # List all mp4 files in the current directory alphabetically
    mp4_files = sorted([os.path.join(tmp_folder, file) for file in os.listdir(tmp_folder) if file.endswith('.mp4')])

    if len(mp4_files) > 0:
        # Create a temporary file listing all mp4 files
        with open(os.path.join(tmp_folder, 'file_list.txt'), 'w') as file_list:
            for mp4_file in mp4_files:
                file_list.write(f"file '{mp4_file}'\n")


        # Concatenate mp4 files using ffmpeg
        output_file_name = os.path.join(output_folder, os.path.basename(path_bag)[:-4] + '.mp4')
        print(f"The video is being saved into: {output_file_name}")
        # -y flag is used to overwrite the output file if it already exists
        # -f concat flag is used to concatenate the files
        # -c copy flag is used to copy the streams without re-encoding
        # -loglevel error flag is used to suppress the ffmpeg output (otherwise it's super annoying and extremely verbose)
        try:
            subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', os.path.join(tmp_folder, 'file_list.txt'), '-c', 'copy', output_file_name, '-loglevel', 'error'])
        except:
            if failed == False:
                failed = "Subprocess ffmpeg failed."
            else:
                failed += "... AND ALSO SUBPROCESS FFMPEG FAILED!."

    # Delete the original mp4 files in the tmp folder
    if os.path.exists(tmp_folder):
        shutil.rmtree(tmp_folder)
    
    return duration, failed, num_frames

def bag_folder2mp4(bag_folder, output_folder, log_table_path):
    # Initialize a DataFrame to log the status
    log_df = pd.DataFrame(columns=['bag_path', 'failed', 'duration', 'num_frames', 'calculated_duration'])

    file_counter = 0
    for root, _, files in os.walk(bag_folder):
        for file in files:
            if file.endswith('.bag'):
                bag_path = os.path.join(root, file)
                duration, failed, num_frames = bag2mp4(bag_path, output_folder)
                log_df.loc[file_counter] = [bag_path, failed, duration, num_frames, num_frames/30]
                file_counter += 1                

    # Save the log table to CSV
    log_df.to_csv(log_table_path, index=False)
    print(f"Log table saved to {log_table_path}")

# path_bag = '/home/mpicek/repos/master_project/test_data/corresponding/bags/2023_11_13/realsense/cam0_911222060374_record_13_11_2023_1337_20.bag'
# output_folder = '/home/mpicek/repos/master_project/test_data/corresponding/bags/2023_11_13/realsense/'
# path_bag = '/data/bags/cam0_916512060805_record_04_10_2023_1354_32.bag'

path_bag = '/data/bags/cam0_916512060805_record_04_10_2023_1341_07.bag'
output_folder = '/data/bags/'

def main():
    # Argument parser setup
    parser = argparse.ArgumentParser(description="Convert bag files to mp4 and log the status.")
    parser.add_argument("bag_folder", help="Path to the folder containing bag files.")
    parser.add_argument("output_folder", help="Path to the output folder for mp4 files.")
    parser.add_argument("log_table_path", help="Path to save the log table as a CSV file.")
    args = parser.parse_args()

    # if we want to process just one file (in that case args.bag_folder has to be a path to the file)
    # failed = bag2mp4(args.bag_folder, args.output_folder)
    # print(failed)
    bag_folder2mp4(args.bag_folder, args.output_folder, args.log_table_path)

if __name__ == "__main__":
    main()