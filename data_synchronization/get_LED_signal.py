import numpy as np
import cv2
import os
import argparse
import plotly.graph_objects as go
import pandas as pd
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter
def smooth(y, box_pts):
    return gaussian_filter(y, box_pts)
from wisci_utils import get_LED_data
from LED_utils import get_LED_signal_from_video
from LED_video_main import crop_subsampled_LED_red_channel_from_video_for_std


def mp4_get_LED_signal(path_mp4, led_position=None, binary_mask=None):

    n_frames = 9999999999999999999
    downscale_factor = 2
    downsample_frames_factor = 1

    if led_position is None or binary_mask is None:
        subsampled_video_array, led_position, _ = crop_subsampled_LED_red_channel_from_video_for_std(
            path_mp4,
            100,
            downscale_factor,
            downsample_frames_factor
        )

        binary_mask = np.full((subsampled_video_array.shape[1], subsampled_video_array.shape[2]), True)

    average_values = get_LED_signal_from_video(path_mp4, binary_mask, led_position, n_frames, downscale_factor)

    return average_values


def mp4_folder_get_LED(mp4_folder, led_position_folder, output_folder):

    # create the output_folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    processed_files = os.listdir(output_folder)
    processed_mp4_files = [os.path.basename(file)[:-len('_LED_signal.npy')] + '.mp4' for file in processed_files if file.endswith('_LED_signal.npy')]

    for root, _, files in os.walk(mp4_folder):
        for file in files:
            if file.endswith('.mp4'):
                path_mp4 = os.path.join(root, file)

                if os.path.basename(path_mp4) in processed_mp4_files:
                    print(f"File {path_mp4} already processed. Skipping")
                    continue

                print("Processing file:", path_mp4)
                try: # this fails if there is no led_position and binary_mask files => we have to select it manually now
                    led_position = np.load(os.path.join(led_position_folder, os.path.basename(path_mp4)[:-4] + '_LED_position.npy'))
                    binary_mask = np.load(os.path.join(led_position_folder, os.path.basename(path_mp4)[:-4] + '_LED_binary_mask.npy'))
                    led_signal = mp4_get_LED_signal(path_mp4, led_position, binary_mask)
                except Exception as e:
                    led_signal = mp4_get_LED_signal(path_mp4)

                mp4_basename = os.path.basename(path_mp4)[:-4]
                np.save(os.path.join(output_folder, mp4_basename + '_LED_signal.npy'), led_signal)


def main(mp4_folder, led_position_folder, output_folder):

    # if we want to process just one file (in that case args.mp4_folder has to be a path to the file)
    # average_values = mp4_get_LED_signal(args.mp4_folder)
    # import matplotlib.pyplot as plt
    # plt.plot(np.arange(len(average_values)) / 25, average_values)
    # plt.xlabel('Time (s)')
    # plt.ylabel('Average pixel value')
    # plt.title('Average pixel value over time')
    # plt.show()

    mp4_folder_get_LED(mp4_folder, led_position_folder, output_folder)

if __name__ == "__main__":
    # Argument parser setup
    parser = argparse.ArgumentParser(description="Extract the LED signals from .mp4 files.")
    parser.add_argument("mp4_folder", help="Path to the folder containing mp4 files.")
    parser.add_argument("led_position_folder", help="Path to the folder containing led position .npy files.")
    parser.add_argument("output_folder", help="Path to the output folder LED signals.")
    args = parser.parse_args()
    main(args.mp4_folder, args.led_position_folder, args.output_folder)