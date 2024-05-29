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

import numpy as np
import websockets
import requests

import socket
import sys


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
        self.measurement_counter = 0
        self.measurement_previous = None  # np.zeros((1,1),dtype=np.float32)
        self.measurement_current = None  # np.zeros((1,1),dtype=np.float32)

        self.index_of_loop = 0  # this is to loop around the frequencies
        self.found_gain = None  # 0
        self.found_frequency =  self.center_freq # frequency_range[0]  #

        self.sock = None
        self.server_address = None
        # self.profiler_counter = 0
        self.lost_counter = 0 #ilhami

    def get_frequencies(self):
        lower_limit = self.frequency_range[0]
        upper_limit = self.frequency_range[1]
        bandwith = self.bandwidth

        freqs = np.arange(
            lower_limit + bandwith / 2, upper_limit - bandwith / 2, bandwith / 1
        )
        self.freqs = freqs
        return

    def get_frequencies_around_center(self):
        center_freq = self.found_frequency
        bandwith = self.bandwidth

        freqs = np.arange(
            max(center_freq - bandwith * 3.5, self.frequency_range[0]),
            min(center_freq + bandwith * 4, self.frequency_range[1]),
            bandwith / 1,
        )
        # print(freqs)
        self.freqs = freqs
        return
    
    def get_random_frequencies(self):
        freqs = np.random.randint(2800e6, 3800e6, 10)
        self.freqs = freqs
        return
    
    def process_measurement(self, measurement):

        
        if self.measurement_counter < len(self.freqs):
            self.measurement_counter = self.measurement_counter + 1
            
            self.measured_power_list.append(np.max(measurement))
            self.measured_frequency_list.append(self.freqs[self.index_of_loop])

        else:
            self.found_gain = np.max(self.measured_power_list)
            self.found_frequency = self.measured_frequency_list[0]
            self.measured_power_list = []
            self.measured_frequency_list = []
            self.measurement_counter = 0

            if self.found_gain > self.threshold_gain:
                # publish the found frequency and gain
                print("Found frequency: ", self.found_frequency)
                print("Found gain: ", self.found_gain)

                message = str(self.found_frequency) + "," + str(self.found_gain) + "\n"
                self.sock.sendto(message.encode(), self.server_address)

                self.found_gain = None
                self.found_frequency = self.center_freq
        

        self.index_of_loop = self.index_of_loop + 1

        if self.index_of_loop == len(self.freqs):
            self.index_of_loop = 0

        self.center_freq = self.freqs[self.index_of_loop]
        self.change_center_freq()

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

    def change_bandwidth(self):
        """
        Change the bandwidth of the SDR by sending a request to the Maia SDR.
        """
        json = {"bandwidth": self.bandwidth}
        response = requests.patch(self.http_adress + "/api/ad9361", json=json)
        if response.status_code != 200:
            print(response.text)
            sys.exit(1)
        else:
            return True

    def UDP_init(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_address = ("localhost", 10010)
        return


def setup_maiasdr(args):
    response = requests.patch(
        args.http_address + "/api/ad9361",
        json={
            "sampling_frequency": args.samp_rate,
            "rx_rf_bandwidth": args.bandwidth,
            "rx_lo_frequency": int(args.frequency_range[0]),
            'rx_gain': args.rx_gain,
            "rx_gain_mode": "Manual",
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


async def spectrum_loop(address, finder):
    async with websockets.connect(address) as ws:
        while True:
            spec = np.frombuffer(await ws.recv(), "float32")
            power_arry = 10 * np.log10(spec)
            finder.process_measurement(power_arry)


def main_async(ws_address, finder):
    asyncio.run(spectrum_loop(ws_address, finder))


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
        default=60,
        help="RX gain [default=%(default)r] dB",
        required=False,
    )
    parser.add_argument(
        "--bandwidth",
        type=int,
        default=int(56e6), # TODO
        help="bandwidth [default=%(default)r]",
        required=False,
    )
    parser.add_argument(
        "--samp_rate",
        type=int,
        default=int(61e6),
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
        default=80,
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
    # emitter.get_frequencies_around_center()
    emitter.get_random_frequencies()
    emitter.UDP_init()

    loop = threading.Thread(target=main_async, args=(waterfall_address, emitter))
    loop.start()


if __name__ == "__main__":
    main()
