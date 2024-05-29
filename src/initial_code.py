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
        self.measurement_counter = False
        self.measurement_previous = None  # np.zeros((1,1),dtype=np.float32)
        self.measurement_current = None  # np.zeros((1,1),dtype=np.float32)

        self.index_of_loop = 0  # this is to loop around the frequencies
        self.found_gain = None  # 0
        self.found_frequency = frequency_range[0]  # self.center_freq

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
            max(center_freq - bandwith * 0.5, self.frequency_range[0]),
            min(center_freq + bandwith * 1, self.frequency_range[1]),
            bandwith / 2,
        )
        # print(freqs)
        self.freqs = freqs
        return
    

    def process_measurement(self, measurement):
        if self.measurement_counter == False:
            self.measurement_counter = True
            self.measurement_previous = measurement
            return
        
        self.measurement_counter = False
        # average the two measurements
        self.measurement_current = np.divide(
            np.add(self.measurement_previous, measurement), 2
        )

        max_power = np.max(self.measurement_current)
        # TODO: check frequency bins
        frequency_max_power = (
            self.center_freq
        )  # + np.argmax(self.measurement_current) - (self.measurement_current.size/2)

        self.measured_power_list.append(max_power)
        self.measured_frequency_list.append(frequency_max_power)

        # decision part
        if self.center_freq == self.freqs[-1]:
            # these comments are left for profiling., otherwise the code would run forever
            # self.profiler_counter = self.profiler_counter + 1
            # if self.profiler_counter == 50:
            # sys.exit(1)

            value_of_this_scan = max(self.measured_power_list)
            # check if it is an update value
            
            if value_of_this_scan > self.threshold_gain:
                self.found_gain = value_of_this_scan
                self.found_frequency = self.measured_frequency_list[
                    self.measured_power_list.index(value_of_this_scan)
                ]
                ## These print statements are left for debugging purposes
                # print("Found frequency = ", self.found_frequency)
                # print("Found Gain = ", self.found_gain)
                # send the found frequency and gain to the UDP server
                message = str(self.found_frequency) + "," + str(self.found_gain) + "\n"
                self.sock.sendto(message.encode(), self.server_address)
                
                if self.wide == True:
                    self.wide = False
                    self.bandwidth = 18e6
                    self.change_bandwidth()

                #following part of this if block is added to ensure we lost the signal (ilhami)
                self.lost_counter = 0 # added

            else:
                # in this case this means we lost it
                #this else code is manipulated to ensure we lost the signal. Older version is zipped. (ilhami)
                self.lost_counter += 1
                if self.lost_counter == 5:
                    self.lost_counter = 0
                    self.wide = True
                    self.bandwidth = 54e6
                    self.change_bandwidth()

                    message = str(self.found_frequency) + ",1500\n" # lost message with last frequency
                    self.sock.sendto(message.encode(), self.server_address)
                else:
                    message = str(self.found_frequency) + "," + str(self.found_gain) + "\n"
                    self.sock.sendto(message.encode(), self.server_address)
                    self.wide = False

                    

                print("Lost the signal",self.lost_counter)

            if self.wide == True:
                self.get_frequencies()
            else:
                self.get_frequencies_around_center()
            # reset lists
            self.measured_frequency_list = []
            self.measured_power_list = []
            self.index_of_loop = 0

        else:
            self.index_of_loop = self.index_of_loop + 1

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
        default=int(18e6), # TODO
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
        default=20,
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

    loop = threading.Thread(target=main_async, args=(waterfall_address, emitter))
    loop.start()


if __name__ == "__main__":
    main()
