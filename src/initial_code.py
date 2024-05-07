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

import sys

class emitter_finder:
    def __init__(self, center_freq, rx_gain, bandwidth, samp_rate, spectrum_rate, ws_address, frequency_range, threshold_gain):
        self.center_freq = center_freq
        self.rx_gain = rx_gain
        self.bandwidth = bandwidth
        self.samp_rate = samp_rate
        self.spectrum_rate = spectrum_rate
        self.ws_address = ws_address # websocket address base (non waterfall part)
        self.frequency_range = frequency_range
        
        self.threshold_gain = threshold_gain
        self.wide = True # if False it will be narrow a.k.a frequencies around center
        self.freqs = np.zeros(1,1)
        self.measured_frequency_list = []
        self.measured_power_list = []
        self.measurement_counter = False
        self.measurement_previous = np.zeros(1,1)
        self.measurement_current = np.zeros(1,1)
        
        self.index_of_loop = 0 # this is to loop around the frequencies
        self.found_gain = 0
        self.found_frequency = self.center_freq

    def get_frequencies(self):
        lower_limit = self.frequency_range[0]
        upper_limit = self.frequency_range[1]
        bandwith = self.bandwidth

        freqs = np.arange(lower_limit + bandwith/2, upper_limit - bandwith/2, bandwith)
        self.freqs = freqs
        return freqs

    def get_frequencies_around_center(self):
        center_freq = self.found_frequency
        bandwith = self.bandwidth

        freqs = np.arange(center_freq - bandwith * 2.5, center_freq + bandwith * 2.5, bandwith)
        self.freqs = freqs
        return freqs
    def process_measurement(self, measurement):
        if self.measurment_counter == False:
            self.measurement_counter = True
            self.measurement_previous = measurement
            return 
        else:
            self.measurement_counter = False
            # average the two measurements
            self.measurement_current = np.divide(np.sum(self.measurement_previous, measurement), 2)
            
            max_power = max(self.measurement_current)
            # TODO: check frequency bins
            frequency_max_power = self.center_freq + self.measurement_current.index(max_power) - (len(self.measurement_current)/2)

            self.measured_power_list.append(max_power)
            self.measured_frequency_list.append(frequency_max_power)

            # decision part
            if self.center_freq == self.freqs[-1]:
                value_of_this_scan = max(self.measured_power_list)
                # check if it is an update value
                if value_of_this_scan > self.threshold_gain:
                    self.found_gain = value_of_this_scan
                    self.found_frequency = self.measured_frequency_list.index(value_of_this_scan)
                    self.wide = False
                # in this case this means we lost it
                else:
                    self.wide = True
                
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
            return            
    def change_center_freq(self):
        
        """
        Change the center frequency of the SDR by sending a request to the Maia SDR.
        """
        json = {
            "rx_lo_frequency": self.center_freq
        }
        response = requests.patch(
            self.ws_address + '/api/ad9361',
            json=json)
        if response.status_code != 200:
            print(response.text)
            sys.exit(1)
        else:
            return True


def setup_maiasdr(args):
    response = requests.patch(
        args.maiasdr_url + '/api/ad9361',
        json={
            'sampling_frequency': args.samp_rate,
            'rx_rf_bandwidth': args.samp_rate,
            'rx_lo_frequency': args.center_freq,
            'rx_gain': args.rx_gain,
            'rx_gain_mode': 'Manual',
        })
    if response.status_code != 200:
        print(response.text)
        sys.exit(1)
    response = requests.patch(
        args.ws_adress + '/api/spectrometer',
        json={
            'output_sampling_frequency': args.spectrum_rate,
        })
    if response.status_code != 200:
        print(response.text)
        sys.exit(1)



async def spectrum_loop(address, finder):
    async with websockets.connect(address) as ws:
        while True:   
            spec = np.frombuffer(await ws.recv(), 'float32')
            power_arry = 10*np.log10(spec)
            finder.process_measurement(power_arry)



def main_async(ws_address, finder):
    asyncio.run(spectrum_loop(ws_address, finder))




def parse_args():
    parser = argparse.ArgumentParser(
        description='Emitter finter over waterfall using Maia SDR')
    parser.add_argument('--center_freq', type=int, default=int(3000e6),
                        help='Center frequency [default=%(default)r]')
    parser.add_argument('--rx_gain', type=int, default=10,
                        help='RX gain [default=%(default)r] dB')
    parser.add_argument('--bandwidth', type=int, default=int(54e6),
                        help='bandwidth [default=%(default)r]')
    parser.add_argument('--samp_rate', type=int, default=int(18e6),
                        help='Sampling rate [default=%(default)r]')
    parser.add_argument('--spectrum_rate', type=float, default=100,
                        help='Spectrum rate [default=%(default)r] Hz')
    parser.add_argument('--ws_address', type=str,
                        help='websocket server address', default="")
    parser.add_argument('--frequency_range', type=list, default=[2800e6, 3800e6],
                        help='Frequency range for emitter detection [default=%(default)r] Hz')
    parser.add_argument('--threshold_gain', type=int, default=40,
                        help='Threshold to decide whether the device is found or not')
    return parser.parse_args()

def main():
    args = parse_args()
    setup_maiasdr(args)
    waterfall_adress = args.ws_adress + "/waterfall"

    emitter = emitter_finder(args.center_freq, args.rx_gain, args.bandwidth, args.samp_rate, args.spectrum_rate, args.ws_adress, args.frequency_range)
    emitter.get_frequencies()
    
    loop = threading.Thread(target=main_async, args=(waterfall_adress, emitter_finder))
    loop.start()


    
if __name__ == '__main__':
    main()
