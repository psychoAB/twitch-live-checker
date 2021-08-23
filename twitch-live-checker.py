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
import queue

#================================================

RETRY_LIMIT = 5
RETRY_INTERVAL = 0.5
MAIN_THREAD_INTERVAL = 0.2
REQUEST_PER_SECOND_LIMIT = 5

DEFAULT_CONFIG_FILE_PATH = pathlib.Path.home() / pathlib.Path( '.twitch-live-checker.conf' )
DEFAULT_THREAD_NUM_MAX = 1

#================================================

class StreamerStatus( enum.Enum ):
    waiting     = 'Waiting'
    checking    = 'Checking'
    retrying    = 'Retrying'
    live        = 'Live'
    offline     = 'Offline'
    not_found   = 'Not Found'

#================================================

request_count_lock = threading.Lock()

streamer_queue = queue.SimpleQueue()

is_disconnected = False

request_count = 0
    
#================================================

def main():

    global request_count

    if len( sys.argv ) > 1:
        config_file_path = sys.argv[ 1 ]
    else:
        config_file_path = DEFAULT_CONFIG_FILE_PATH

    config_file_text = read_config_file( config_file_path )
    
    ( thread_num_max, streamer_list, username_not_valid_list ) = parse_config( config_file_text )
    
    streamer_status_dict = dict.fromkeys( streamer_list, StreamerStatus.waiting )
    streamer_retry_count_dict = dict.fromkeys( streamer_list, 0 )

    for streamer in streamer_list:
        streamer_queue.put( streamer )

    time_request_count_refresh_prev = time.time()
    
    while ( streamer_queue.empty() == False ) or ( threading.activeCount() > 1 ):

        while ( streamer_queue.empty() == False ) and ( threading.activeCount() < thread_num_max + 1 ) and ( request_count < REQUEST_PER_SECOND_LIMIT ):
            streamer = streamer_queue.get()

            if streamer_retry_count_dict[ streamer ] < RETRY_LIMIT:
                threading.Thread( target = check_streamer_status, args = ( streamer, streamer_status_dict ) ).start()
                
                streamer_retry_count_dict[ streamer ] += 1
            else:
                streamer_status_dict[ streamer ] = StreamerStatus.not_found

        print_main_output( streamer_status_dict, username_not_valid_list )

        time_current = time.time()

        if ( time_current - time_request_count_refresh_prev ) >= 1:
            
            request_count_lock.acquire()

            request_count = 0;

            request_count_lock.release()

            time_request_count_refresh_prev = time_current

        time.sleep( MAIN_THREAD_INTERVAL )

    if is_disconnected == False:
        print_main_output( streamer_status_dict, username_not_valid_list )

#================================================

def check_streamer_status( streamer, streamer_status_dict ):

    global request_count

    streamer_status_dict[ streamer ] = StreamerStatus.checking

    streamer_html_content = get_streamer_html_content( streamer )

    request_count_lock.acquire()

    request_count += 1

    request_count_lock.release()

    if streamer_html_content.find( 'isLiveBroadcast' ) != -1:
        streamer_status_dict[ streamer ] = StreamerStatus.live
    else:
        if streamer_html_content.find( streamer ) != -1:
            streamer_status_dict[ streamer ] = StreamerStatus.offline
        else:
            streamer_status_dict[ streamer ] = StreamerStatus.retrying

            time.sleep( RETRY_INTERVAL )

            streamer_queue.put( streamer )

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

def parse_config( config_file_text ):

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
