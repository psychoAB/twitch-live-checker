#!/bin/python
import urllib.request
import sys
import socket
import time
import re
import os
import threading
import enum
import pathlib

#================================================

RETRY_LIMIT = 3
RETRY_INTERVAL = 0.5
MAIN_THREAD_INTERVAL = 0.2

DEFAULT_CONFIG_FILE_PATH = pathlib.Path.home() / pathlib.Path( '.twitch-live-checker.conf' )
DEFAULT_THREAD_NUM_MAX = 1

is_disconnected = False

class StreamerStatus( enum.Enum ):
    waiting     = 'Waiting'
    checking    = 'Checking'
    live        = 'Live'
    offline     = 'Offline'
    not_found   = 'Not Found'

#================================================

def main():

    if len( sys.argv ) > 1:
        config_file_path = sys.argv[ 1 ]
    else:
        config_file_path = DEFAULT_CONFIG_FILE_PATH

    config_file_text = read_config_file( config_file_path )
    
    ( thread_num_max, streamer_list, username_not_valid_list ) = parse_config_file( config_file_text )
    
    streamer_status_dict = dict.fromkeys( streamer_list, StreamerStatus.waiting )

    while ( len( streamer_list ) > 0 ) or ( threading.activeCount() > 1 ):

        while ( len( streamer_list ) > 0 ) and ( threading.activeCount() < thread_num_max + 1 ):
            threading.Thread( target = check_streamer_status, args = ( streamer_list.pop( 0 ), streamer_status_dict ) ).start()

        print_main_output( streamer_status_dict, username_not_valid_list )

        time.sleep( MAIN_THREAD_INTERVAL )

    if is_disconnected == False:
        print_main_output( streamer_status_dict, username_not_valid_list )

#================================================

def check_streamer_status( streamer, streamer_status_dict ):
    should_retry = True
    retry_count = 0

    streamer_status_dict[ streamer ] = StreamerStatus.checking

    while should_retry == True and retry_count < RETRY_LIMIT:

        streamer_html_content= get_streamer_html_content( streamer )

        if streamer_html_content.find( 'isLiveBroadcast' ) != -1:
            streamer_status_dict[ streamer ] = StreamerStatus.live

            should_retry = False
        else:
            if streamer_html_content.find( streamer ) != -1:
                streamer_status_dict[ streamer ] = StreamerStatus.offline

                should_retry = False
            else:
                retry_count = retry_count + 1

                time.sleep( RETRY_INTERVAL )

    if retry_count >= RETRY_LIMIT:
        streamer_status_dict[ streamer ] = StreamerStatus.not_found

#================================================

def get_streamer_html_content( streamer ):

    global is_disconnected

    try:
        streamer_html_content = urllib.request.urlopen( 'https://www.twitch.tv/' + streamer ).read().decode( 'utf-8' )
    except urllib.error.URLError as error:
        if type( error.reason ) == socket.gaierror:
            if is_disconnected == False:
                is_disconnected = True

                print_to_stderr( str( error ) )

                print_to_stderr( 'Check your network connection.' )

            quit( error.reason.errno )

    return streamer_html_content

#================================================

def parse_config_file( config_file_text ):

    config_file_text_line = config_file_text.split( '\n' )

    config_file_text_line = list( filter( lambda line : line != '', config_file_text_line ) )

    if len( config_file_text_line ) > 0:
        if re.fullmatch( '[1-9][0-9]*', config_file_text_line[ 0 ] ) != None:
            thread_num_max = int( config_file_text_line[ 0 ] )

            config_file_text_line = config_file_text_line[ 1 : ]
        else:
            thread_num_max = DEFAULT_THREAD_NUM_MAX

    username_not_valid_list = list( filter( lambda line : re.fullmatch( '[a-zA-Z0-9]\w{3,24}', line ) == None , config_file_text_line ) )
    streamer_list = list( filter( lambda line : line not in username_not_valid_list , config_file_text_line ) )

    return ( thread_num_max, streamer_list, username_not_valid_list )

#================================================

def read_config_file( config_file_path ):
    try:
        config_file = open( config_file_path, 'r' )
    except FileNotFoundError as error:
        print_to_stderr( str( error ) )
    
        quit( error.errno )
    
    config_file_text = config_file.read()
    
    config_file.close()

    return config_file_text

#================================================

def print_main_output( streamer_status_dict, username_not_valid_list ):
    if len( streamer_status_dict ) > 0:
        clear_screen()

        streamer_string_length_max = max( map( len, streamer_status_dict.keys() ) )

        for streamer in streamer_status_dict.keys():
            print_streamer_status( streamer, streamer_status_dict[ streamer ].value, streamer_string_length_max )
    else:
        print_to_stderr( 'No streamer to check, check your configuration file.' )

    for username in username_not_valid_list:
        print_to_stderr( '"' + username + '"' + " does NOT follow the Twitch's username rules." )

#================================================

def print_streamer_status( streamer, streamer_status, streamer_string_length_max ):
    print( '{}\t'.format( streamer.ljust( streamer_string_length_max ) ) + streamer_status )

#================================================

def print_to_stderr( message ):
    print( message, file = sys.stderr )

#================================================

def clear_screen():
    if os.name == 'nt':
        os.system( 'cls' )
    else:
        os.system( 'clear') 

#================================================

if __name__ == '__main__':
    main()
