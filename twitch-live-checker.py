#!/usr/bin/python

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
REQUEST_TIMEOUT = 3

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

lock_streamer_status_dict = threading.Lock()
lock_time_streamer_request_prev_dict = threading.Lock()

streamer_queue = queue.SimpleQueue()

thread_exception = None

#================================================

def main():

    ( thread_num_max, streamer_list, username_not_valid_list ) = get_config()
    
    streamer_status_dict = dict.fromkeys( streamer_list, StreamerStatus.waiting )
    streamer_retry_count_dict = dict.fromkeys( streamer_list, 0 )
    time_streamer_request_prev_dict = {}

    for streamer in streamer_list:
        streamer_queue.put( streamer )

    time_request_count_refresh_prev = time.time()

    request_count = 0
    
    while ( ( streamer_queue.empty() == False ) or ( threading.active_count() > 1 ) or ( len( time_streamer_request_prev_dict ) > 0 ) ) and ( thread_exception == None ):

        lock_time_streamer_request_prev_dict.acquire()

        streamer_retrying_ready_list = list( filter( lambda streamer : ( time.time() - time_streamer_request_prev_dict[ streamer ] ) >= RETRY_INTERVAL, time_streamer_request_prev_dict ) )

        for streamer in streamer_retrying_ready_list:
            del time_streamer_request_prev_dict[ streamer ]

        lock_time_streamer_request_prev_dict.release()

        streamer_not_found_list = list( filter( lambda streamer : streamer_retry_count_dict[ streamer ] >= RETRY_LIMIT, streamer_retrying_ready_list ) )
        streamer_retrying_ready_list = list( filter( lambda streamer : streamer not in streamer_not_found_list, streamer_retrying_ready_list ) )

        for streamer in streamer_retrying_ready_list:
            streamer_queue.put( streamer )

        for streamer in streamer_not_found_list:
            lock_streamer_status_dict.acquire()

            streamer_status_dict[ streamer ] = StreamerStatus.not_found

            lock_streamer_status_dict.release()

        while ( streamer_queue.empty() == False ) and ( threading.active_count() < thread_num_max + 1 ) and ( request_count < REQUEST_PER_SECOND_LIMIT ):
            streamer = streamer_queue.get()

            threading.Thread( target = check_streamer_status, args = ( streamer, streamer_status_dict, time_streamer_request_prev_dict ), daemon = True ).start()

            request_count += 1
            
            streamer_retry_count_dict[ streamer ] += 1

        print_main_output( streamer_status_dict, username_not_valid_list )

        time_current = time.time()

        if ( time_current - time_request_count_refresh_prev ) >= 1:
            
            request_count = 0

            time_request_count_refresh_prev = time_current

        time.sleep( MAIN_THREAD_INTERVAL )

    print_main_output( streamer_status_dict, username_not_valid_list )

    if thread_exception != None:
        if ( type( thread_exception ) == urllib.error.URLError ) and ( type( thread_exception.reason ) == socket.gaierror ):
            print_to_stderr( str( thread_exception ) )

            print_to_stderr( 'Check your network connection.' )

            quit( thread_exception.reason.errno )
        else:
            raise thread_exception

#================================================

def check_streamer_status( streamer, streamer_status_dict, time_streamer_request_prev_dict ):

    lock_streamer_status_dict.acquire()
    
    streamer_status_dict[ streamer ] = StreamerStatus.checking

    lock_streamer_status_dict.release()

    streamer_status = StreamerStatus.checking

    streamer_html_content = get_streamer_html_content( streamer )

    time_streamer_request_prev = time.time()

    if streamer_html_content.find( 'isLiveBroadcast' ) != -1:
        streamer_status = StreamerStatus.live
    else:
        if streamer_html_content.find( streamer ) != -1:
            streamer_status = StreamerStatus.offline
        else:
            streamer_status = StreamerStatus.retrying

            lock_time_streamer_request_prev_dict.acquire()

            time_streamer_request_prev_dict[ streamer ] = time_streamer_request_prev

            lock_time_streamer_request_prev_dict.release()

    lock_streamer_status_dict.acquire()
    
    streamer_status_dict[ streamer ] = streamer_status

    lock_streamer_status_dict.release()

#================================================

def get_streamer_html_content( streamer ):

    global thread_exception

    try:
        streamer_html_content = urllib.request.urlopen( 'https://www.twitch.tv/' + streamer, None, REQUEST_TIMEOUT ).read().decode( 'utf-8' )
    except urllib.error.URLError as error:
        if type( error.reason ) == TimeoutError:
            streamer_html_content = ''
        else:
            thread_exception = error

            quit()
    except TimeoutError as error:
        streamer_html_content = ''
    except Exception as error:
        thread_exception = error

        quit()

    return streamer_html_content

#================================================

def get_config():

    config_file_path = DEFAULT_CONFIG_FILE_PATH

    if len( sys.argv ) > 1:
        config_file_path = sys.argv[ 1 ]

    config_file_text = read_config_file( config_file_path )

    return parse_config( config_file_text )

#================================================

def parse_config( config_file_text ):

    config_file_text_line = config_file_text.split( '\n' )

    config_file_text_line = list( filter( lambda line : line != '', config_file_text_line ) )

    thread_num_max = DEFAULT_THREAD_NUM_MAX

    if len( config_file_text_line ) > 0:
        if re.fullmatch( '[1-9][0-9]*', config_file_text_line[ 0 ] ) != None:
            thread_num_max = int( config_file_text_line[ 0 ] )

            config_file_text_line = config_file_text_line[ 1 : ]

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

        lock_streamer_status_dict.acquire()

        streamer_string_length_max = max( map( len, streamer_status_dict.keys() ) )

        for streamer in streamer_status_dict.keys():
            print_streamer_status( streamer, streamer_status_dict[ streamer ].value, streamer_string_length_max )

        lock_streamer_status_dict.release()
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
