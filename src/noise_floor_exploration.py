"""
Author: Ahmet Akman 
Date: 07.05.2024
-------------------
The purpose of this code is to generate the first version of client software of the SDR to be used in DFV project.

The DFV (Direction Finding Vehicle) is a senior design one of the projects carried out in METU Department of Electrical and Electronics Engineering in 2023Fall-2024Spring semesters. 
.

Group Members: Ahmet Akman, İlhami Selvi, Mustafa Önsoy, Deniz Soysal, Nazmi Yaşıtlı
"""

"""
Pluto-SDR basic parameter limits.
---------------------------------------
Center Frequency(MHz): [325 3800]
Center Frequency Step Size (Hz): 2.4
RF Bandwith (MHz): [0.2 20]
Data-rate (MSPS): [0.651 61.44]
"""

"""
Tuneable parameters of SDR.
The selected ones are simply arbitrary. Only consideration is sampling frequency is three times bandwith.
--------------------------------------
RF Bandwith = 18 # MHz
Sampling Frequency (Data-rate) = 54 # MHz
RX Frequency = [2800 3800] # MHz
RX AGC = "Manual" # No AGC
Hardware Gain = 10 # dB
Spectrum Rate = 100-120 # Hz, MAX~203 Hz
"""

import argparse
import asyncio
import threading
import select

import numpy as np
import websockets
import requests

import socket
import sys

import matplotlib.pyplot as plt

class emitter_finder:
    def __init__(
        self,
        center_freq,
        rx_gain,
        bandwidth,
        samp_rate,
        spectrum_rate,
        ws_address,
        http_address,
        frequency_range,
        threshold_gain,
    ):
        self.center_freq = center_freq
        self.rx_gain = rx_gain
        self.bandwidth = bandwidth
        self.samp_rate = samp_rate
        self.spectrum_rate = spectrum_rate
        self.ws_address = ws_address  # websocket address base (non waterfall part)
        self.http_adress = http_address
        self.frequency_range = frequency_range

        self.threshold_gain = threshold_gain
        self.wide = True  # if False it will be narrow a.k.a frequencies around center
        self.freqs = None
        self.measured_frequency_list = []
        self.measured_power_list = []
        self.measurement_counter = False
        self.measurement_previous = None  # np.zeros((1,1),dtype=np.float32)
        self.measurement_current = None  # np.zeros((1,1),dtype=np.float32)

        self.index_of_loop = 0  # this is to loop around the frequencies
        self.found_gain = None  # 0
        self.found_frequency = frequency_range[0]  # self.center_freq

        self.sock = None
        self.server_address = None
        # self.profiler_counter = 0

    def get_frequencies(self):
        lower_limit = self.frequency_range[0]
        upper_limit = self.frequency_range[1]
        bandwith = self.bandwidth

        freqs = np.arange(
            lower_limit + bandwith / 2, upper_limit - bandwith / 2, bandwith / 1.5
        )
        self.freqs = freqs
        return

    def get_frequencies_around_center(self):
        center_freq = self.found_frequency
        bandwith = self.bandwidth

        freqs = np.arange(
            max(center_freq - bandwith * 1.0, self.frequency_range[0]),
            min(center_freq + bandwith * 1.0, self.frequency_range[1]),
            bandwith / 1.5,
        )
        self.freqs = freqs
        return

    def change_center_freq(self):
        """
        Change the center frequency of the SDR by sending a request to the Maia SDR.
        """
        json = {"rx_lo_frequency": int(self.center_freq)}
        response = requests.patch(self.http_adress + "/api/ad9361", json=json)
        if response.status_code != 200:
            print(response.text)
            sys.exit(1)
        else:
            return True

    def UDP_init(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_address = ("localhost", 10000)
        return


def setup_maiasdr(args):
    response = requests.patch(
        args.http_address + "/api/ad9361",
        json={
            "sampling_frequency": args.samp_rate,
            "rx_rf_bandwidth": args.bandwidth,
            "rx_lo_frequency": int(args.frequency_range[0]),
            # 'rx_gain': args.rx_gain,
            "rx_gain_mode": "FastAttack",
        },
    )
    if response.status_code != 200:
        print(response.text)
        sys.exit(1)
    response = requests.patch(
        args.http_address + "/api/spectrometer",
        json={
            "output_sampling_frequency": args.spectrum_rate,
            "mode": "Average",
        },
    )
    if response.status_code != 200:
        print(response.text)
        sys.exit(1)


async def spectrum_loop(address, line, finder):
    async with websockets.connect(address) as ws:
        i = 0
        while True:
            
            spec = np.frombuffer(await ws.recv(), "float32")
            power_arry = 10 * np.log10(spec)
            line.set_ydata(power_arry)
            
            ready, _, _ = select.select([sys.stdin], [], [], 0.00001)  # Check every 0.1 seconds            
            if ready:
                user_input = sys.stdin.readline().strip()
                if user_input:
                    i += 1
                    if i == len(finder.freqs):
                        i = 0
                    finder.center_freq = finder.freqs[i]
                    finder.change_center_freq()
                    print("center frequency is changed to = ", finder.center_freq)
                    continue


def main_async(ws_address, line, finder):
    asyncio.run(spectrum_loop(ws_address, line, finder))

def prepare_plot(args):
    plt.ion()
    fig = plt.figure()
    ax = fig.add_subplot(111)
    # 4096 points between -bandwidth/2 and +bandwidth/2
    freqs = np.linspace(-args.bandwidth/2, args.bandwidth/2, 4096)
    line, = ax.plot(freqs, np.zeros(freqs.size))
    ax.set_title("gain = "+ str(args.rx_gain))
    ax.set_ylim((10, 100))
    return fig, ax, line


def parse_args():
    parser = argparse.ArgumentParser(
        description="Emitter finter over waterfall using Maia SDR"
    )
    parser.add_argument(
        "--center_freq",
        type=int,
        default=int(3000e6),
        help="Center frequency [default=%(default)r]",
        required=False,
    )
    parser.add_argument(
        "--rx_gain",
        type=int,
        default=10,
        help="RX gain [default=%(default)r] dB",
        required=False,
    )
    parser.add_argument(
        "--bandwidth",
        type=int,
        default=int(18e6),
        help="bandwidth [default=%(default)r]",
        required=False,
    )
    parser.add_argument(
        "--samp_rate",
        type=int,
        default=int(54e6),
        help="Sampling rate [default=%(default)r]",
        required=False,
    )
    parser.add_argument(
        "--spectrum_rate",
        type=float,
        default=160,
        help="Spectrum rate [default=%(default)r] Hz",
        required=False,
    )
    parser.add_argument(
        "--ws_address",
        type=str,
        help="websocket server address",
        default="ws://192.168.2.1:8000",
        required=False,
    )
    parser.add_argument(
        "--http_address",
        type=str,
        help="normal server address",
        default="http://192.168.2.1:8000",
        required=False,
    )
    parser.add_argument(
        "--frequency_range",
        type=list,
        default=[2800e6, 3800e6],
        help="Frequency range for emitter detection [default=%(default)r] Hz",
        required=False,
    )
    parser.add_argument(
        "--threshold_gain",
        type=int,
        default=85,
        help="Threshold to decide whether the device is found or not",
        required=False,
    )
    return parser.parse_args()



def main():
    args = parse_args()

    setup_maiasdr(args)
    waterfall_address = args.ws_address + "/waterfall"

    emitter = emitter_finder(
        args.center_freq,
        args.rx_gain,
        args.bandwidth,
        args.samp_rate,
        args.spectrum_rate,
        args.ws_address,
        args.http_address,
        args.frequency_range,
        args.threshold_gain,
    )
    emitter.get_frequencies()
    emitter.UDP_init()
    fig, ax, line = prepare_plot(args)

    loop = threading.Thread(target=main_async, args=(waterfall_address, line, emitter))
    loop.start()

    plt.show(block=True)



if __name__ == "__main__":
    main()
