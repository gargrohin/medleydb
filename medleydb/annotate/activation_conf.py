"""Generate activation confidence annotations.
"""
from __future__ import division
import scipy.signal
import numpy as np
import librosa
import medleydb
from medleydb.multitrack import _ACTIVATION_CONF_PATH
import os
import argparse


def create_activation_annotation(mtrack, win_len=4096, lpf_cutoff=0.075,
                                 theta=0.15, binarize=False):

    H = []
    index_list = []

    # MATLAB equivalent to @hanning(win_len)
    win = scipy.signal.windows.hann(win_len + 2)[1:-1]

    for stem_idx, track in mtrack.stems.items():
        audio, rate = librosa.load(track.audio_path, sr=44100, mono=True)
        H.append(track_activation(audio.T, win_len, win))
        index_list.append(stem_idx)

    # list to numpy array
    H = np.array(H)

    # normalization (to overall energy and # of sources)
    E0 = np.sum(H, axis=0)
    
    H = len(mtrack.stems) * H / np.max(E0)
    H[:, E0 < 0.01] = 0.0  # binary thresholding for low overall energy events

    # LP filter
    b, a = scipy.signal.butter(2, lpf_cutoff, 'low')
    H = scipy.signal.filtfilt(b, a, H, axis=1)

    # logistic function to semi-binarize the output; confidence value
    H = 1 - 1 / (1 + np.exp(np.dot(20, (H - theta))))

    # binarize output
    if binarize:
        H_out = np.zeros(H.shape)
        H_out[H > 0.5] = 1
    else:
        H_out = H

    # add time column
    time = librosa.core.frames_to_time(
        np.arange(H.shape[1]), sr=rate, hop_length=win_len // 2
    )

    # stack time column to matrix
    H_out = np.vstack((time, H_out))
    return H_out.T, index_list


def track_activation(wave, win_len, win):
    hop_len = win_len // 2

    wave = np.lib.pad(
        wave,
        pad_width=(
            win_len-hop_len,
            0
        ),
        mode='constant',
        constant_values=0
    )

    # post padding
    wave = librosa.util.fix_length(
        wave, int(win_len * np.ceil(len(wave) / win_len))
    )

    # cut into frames
    wavmat = librosa.util.frame(
        wave,
        frame_length=win_len,
        hop_length=hop_len
    )

    # Envelope follower
    wavmat = hwr(wavmat) ** 0.5  # half-wave rectification + compression

    return np.mean((wavmat.T * win), axis=1)


def hwr(x):
    ''' half-wave rectification'''
    return (x + np.abs(x)) / 2


def write_activations_to_csv(mtrack, activations, index_list, debug=False):

    stem_str = ",".join(
        ["S%02d" % stem_idx for stem_idx in index_list]
    )
    np.savetxt(
        mtrack.activation_conf_fpath,
        activations,
        header='time,{}'.format(stem_str),
        delimiter=',',
        fmt='%.4f',
        comments=''
    )


def main(args):
    mtrack = medleydb.MultiTrack(args.track_id)
    if os.path.exists(mtrack.activation_conf_fpath):
        return True

    activations, index_list = create_activation_annotation(mtrack)
    if args.write_output:
        write_activations_to_csv(mtrack, activations, index_list, args.debug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("track_id",
                        type=str,
                        default="LizNelson_Rainfall",
                        help="MedleyDB track id. Ex. LizNelson_Rainfall")
    parser.add_argument("--write_output",
                        type=bool,
                        default=True,
                        help="If true, write the output to a file")
    parser.add_argument("--debug",
                        type=bool,
                        default=True,
                        help="If true, use debug filename output")
    main(parser.parse_args())
