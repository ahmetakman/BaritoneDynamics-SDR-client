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
import matplotlib.pyplot as plt
import websockets







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
        args.maiasdr_url + '/api/spectrometer',
        json={
            'output_sampling_frequency': args.spectrum_rate,
        })
    if response.status_code != 200:
        print(response.text)
        sys.exit(1)



async def spectrum_loop(address):
    async with websockets.connect(address) as ws:
        while True:
            spec = np.frombuffer(await ws.recv(), 'float32')
            power_arry = 10*np.log10(spec)



def main_async(ws_address):
    asyncio.run(spectrum_loop(ws_address))




def parse_args():
    parser = argparse.ArgumentParser(
        description='Emitter finter over waterfall using Maia SDR')
    parser.add_argument('--center_freq', type=int, default=int(3.0e9),
                        help='Center frequency [default=%(default)r]')
    parser.add_argument('--rx_gain', type=int, default=10,
                        help='RX gain [default=%(default)r]')
    parser.add_argument('--samp_rate', type=int, default=int(18e6),
                        help='Sampling rate [default=%(default)r]')
    parser.add_argument('--spectrum_rate', type=float, default=100,
                        help='Spectrum rate [default=%(default)r]')
    parser.add_argument('--ws_address', type=str,
                        help='websocket server address', default="ws://192")
    return parser.parse_args()

def main():
    args = parse_args()
    setup_maiasdr(args)
    loop = threading.Thread(target=main_async, args=(args.ws_adress))
    loop.start()


    
if __name__ == '__main__':
    main()
