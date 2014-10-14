#-------------------------------------------------------------------------------
# Name:        GPADC measure
# Purpose:     TBAT_ICH_charging
#
# Author:      ytam
#
# Created:     10/10/2014
# Copyright:   (c) ytam 2014
#-------------------------------------------------------------------------------
'''
:Equipment:

    -Hameg HM8143
        :variable name:supply
        :description:Supply VBAT board. Connect channel 1 VBAT

    -Keithley 2000
        :variable name:vrtc
        :description:connect to the VRTC test point

    -Votsch VT4002
        :variable name:oven
        :description:

    -Evaluation Board

:Detailed Description: The script
'''
import instruments
from instruments import Hameg814x
from instruments import Keithley2000
from instruments import VT4002

#instrument setup
supply  = Hameg814x.Hameg814x("COM20")
oven 	= VT4002.VT4002("10.20.24.100")
vrtc    = Keithley2000.Keithley2000("GPIB::17")

from utilities import write_results

import uli
import ctypes
import time
import csv
import sys
import serial

# Name of output file
path = '../results/'
filename = 'Die temp'

# Amber registers
REG_ACTIVE1 		= 0x080
REG_ACTIVE3 		= 0x082
REG_ACTIVE4 		= 0x083
REG_ACTIVE6 		= 0x085

REG_MAN_CONTROL_ADC         = 0x500
REG_ADC_OUT_BITS_3_0        = 0x502
REG_ADC_OUT_BITS_11_4       = 0x503

GPADC_DIE_TEMP_CHANNELS = [ 0x88, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99 ]

#port mask
ACC_DET_PIN     = 20
PORTB           = 0
HIGH            = 1
LOW             = 0
OUTPUT          = 1
INPUT           = 0

TIME_OUT = 60000

NO_OF_AVERAGE = 10

#TEMP_SETTINGS = [ -40, -30, -20, -10, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120 ]
TEMP_SETTINGS = [ -40, -20, 0, 20, 40, 60, 80, 100, 120 ]
#TEMP_SETTINGS = [ -40]

VBAT_SETTINGS = 3.8

#Do a manual conversion
def read_GPADC(i2c, mux_address):

    #start off a manual conversion
    i2c.write_register(REG_MAN_CONTROL_ADC, mux_address)
    time.sleep(0.001)

    #get the 4 LSBs of the result
    man_result_bits_3_0 =i2c.read_register(REG_ADC_OUT_BITS_3_0)
    time.sleep(0.05) # 50ms

    #get the 8 MSBs of the result
    man_result_bits_11_4 =i2c.read_register(REG_ADC_OUT_BITS_11_4)
    time.sleep(0.05) # 50ms

    #combine the results into a 12 bit number
    man_result_bits_3_0 = man_result_bits_3_0 & 0x0f
    man_result_bits_11_4 = man_result_bits_11_4 << 4
    man_result = man_result_bits_11_4 | man_result_bits_3_0

    #return the result
    return man_result

#get average of no_of_samples of GPADC results
def man_temp_readout(i2c, channel, no_of_samples):

    man_result = 0

    #sum a no_of_samples results from the GPADC
    for j in range( no_of_samples):
        man_result = man_result + read_GPADC(i2c, channel)
        j=j+1

    #average the summed results
    man_result = man_result / no_of_samples

    #return the average
    return man_result

def GPADC_die_temp():

    # Initialise I2C
    devno = uli.setup()
    i2c = uli.I2C16bit(devno, 0xE8)

    #define the port to wake up the board under test remotely
    port = uli.PORT(devno)

    results_table = []
    result_row = []

    #Set up VBAT to 3.8V on channel 1
    supply.set_v( VBAT_SETTINGS)
    supply.output_enable()
    time.sleep(2)

    #set the state and direction of port pins on the SAM device
    port.setIOState( PORTB, ACC_DET_PIN, HIGH )
    port.setIOMode( PORTB, ACC_DET_PIN, OUTPUT )

    port.setIOState( PORTB, ACC_DET_PIN, LOW )
    time.sleep(1.0)
    port.setIOState( PORTB, ACC_DET_PIN, HIGH )
    time.sleep(1.0)

    # Switch off all regulator outputs
    i2c.write_register(REG_ACTIVE1, 0)
    i2c.write_register(REG_ACTIVE3, 0)
    i2c.write_register(REG_ACTIVE4, 0)
    i2c.write_register(REG_ACTIVE6, 0)

    # initialize oven
    oven.start_chamber()
    oven.write_temp_value(25)

    # outside loop is the chamber temperature settings
    for set_temp in TEMP_SETTINGS:

        # set temperature
        oven.write_temp_value(set_temp)

        while(abs(oven.read_temp()-set_temp) > 1.0 ):
            print oven.read_temp()
            time.sleep(10)

        #wait for device to termally stablise
        time.sleep(600) #10 mins

    	result_row = []

    	result_row.append(supply.read_v( 10))
    	result_row.append(oven.read_temp())
    	result_row.append(vrtc.read_v(10))

        # loop for obtaining GPADC outputs of Die temp sensors
        for read_channel in range( len(GPADC_DIE_TEMP_CHANNELS)):

            #get an average of 10 for each of the temperature channel from the GPADC
            adc_output = man_temp_readout(i2c, GPADC_DIE_TEMP_CHANNELS[read_channel], NO_OF_AVERAGE)

            #store the result
            result_row.append(adc_output)

    	#store each line of results in final table
    	print result_row
    	results_table.append(result_row)

    #switch off VBAT
    supply.output_disable()

    oven.write_temp_value(25)

    #switch off oven
    oven.stop_chamber()

    # Prepare output file & save data
    filename_csv = path+filename+'.csv'
    header=('VBATT','TEMP','VRTC','GPADC_TJINT', 'GPADC_LDO5', 'GPADC_LoadSW', 'GPADC_VCENTER',
	    'GPADC_LCHARGER','GPADC_BUCK0', 'GPADC_BUCK21', 'GPADC_BUCK35', 'GPADC_BUCK14')
    write_results(filename_csv, header, results_table)

    print 'End of Script'

if __name__ == '__main__':
    GPADC_die_temp()
