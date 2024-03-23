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
import html
import signal

#================================================

RETRY_LIMIT = 5
RETRY_INTERVAL = 0.5
REQUEST_PER_SECOND_LIMIT = 5
REQUEST_TIMEOUT = 3
TAG_NOT_FOUND_STRING = 'TAG_NOT_FOUND'

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
lock_exception_thread = threading.Lock()

streamer_queue = queue.SimpleQueue()

exception_thread = None

flag_should_stop = threading.Event()

#================================================

MAX_STREAMER_STATUS_ENUM_LENGTH = max( map( len, [ streamer_status_enum.value for streamer_status_enum in StreamerStatus ] ) )

#================================================

def main():

    signal.signal( signal.SIGINT, handler_interrupt )

    threading.excepthook = hook_exception_thread;

    ( thread_num_max, streamer_list, username_not_valid_list ) = get_config()
    
    streamer_status_dict = { streamer : [ StreamerStatus.waiting, TAG_NOT_FOUND_STRING ] for streamer in streamer_list }
    streamer_retry_count_dict = dict.fromkeys( streamer_list, 0 )
    time_streamer_request_prev_dict = {}

    for streamer in streamer_list:
        streamer_queue.put( streamer )

    thread_render = threading.Thread( target = print_main_output_loop, args = ( streamer_status_dict, username_not_valid_list ), daemon = True )
    thread_render.start()

    time_request_count_refresh_prev = time.time()

    request_count = 0
    
    while ( ( streamer_queue.empty() == False ) or ( threading.active_count() > 2 ) or ( len( time_streamer_request_prev_dict ) > 0 ) ) and ( flag_should_stop.is_set() == False ):

        time_current = time.time()

        if ( time_current - time_request_count_refresh_prev ) >= 1:

            request_count = 0

            time_request_count_refresh_prev = time_current

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

            streamer_status_dict[ streamer ][ 0 ] = StreamerStatus.not_found

            lock_streamer_status_dict.release()

        if ( streamer_queue.empty() == False ) and ( threading.active_count() < thread_num_max + 2 ) and ( request_count < REQUEST_PER_SECOND_LIMIT ):
            streamer = streamer_queue.get()

            threading.Thread( target = check_streamer_status, args = ( streamer, streamer_status_dict, time_streamer_request_prev_dict ), daemon = True ).start()

            request_count += 1
            
            streamer_retry_count_dict[ streamer ] += 1

        time.sleep( 1 / REQUEST_PER_SECOND_LIMIT )

    flag_should_stop.set()
    thread_render.join()

    print_main_output( streamer_status_dict, username_not_valid_list )

    if exception_thread != None:
        if ( type( exception_thread ) == urllib.error.URLError ) and ( type( exception_thread.reason ) == socket.gaierror ):
            print_to_stderr( str( exception_thread ) )

            print_to_stderr( 'Check your network connection.' )

            sys.exit( exception_thread.reason.errno )
        else:
            raise exception_thread

#================================================

def check_streamer_status( streamer, streamer_status_dict, time_streamer_request_prev_dict ):

    lock_streamer_status_dict.acquire()
    
    streamer_status_dict[ streamer ][ 0 ] = StreamerStatus.checking

    lock_streamer_status_dict.release()

    streamer_status = StreamerStatus.checking
    streamer_tag = TAG_NOT_FOUND_STRING

    streamer_html_content = get_streamer_html_content( streamer )

    time_streamer_request_prev = time.time()

    if ( streamer_html_content.find( 'isLiveBroadcast' ) != -1 ) and ( streamer_html_content.find( 'status="offline"' ) == -1 ):
        streamer_status = StreamerStatus.live

        streamer_tag_position_start = streamer_html_content.find( '/directory/category/' )

        if streamer_tag_position_start != -1:
            streamer_tag_position_start = streamer_html_content.find( '>', streamer_tag_position_start + 1 ) + 1
            streamer_tag_position_end = streamer_html_content.find( '<', streamer_tag_position_start + 1 )

            streamer_tag = streamer_html_content[ streamer_tag_position_start : streamer_tag_position_end ]
            streamer_tag = html.unescape(streamer_tag)
    else:
        if streamer_html_content.find( streamer ) != -1:
            streamer_status = StreamerStatus.offline
        else:
            streamer_status = StreamerStatus.retrying

            lock_time_streamer_request_prev_dict.acquire()

            time_streamer_request_prev_dict[ streamer ] = time_streamer_request_prev

            lock_time_streamer_request_prev_dict.release()

    lock_streamer_status_dict.acquire()
    
    streamer_status_dict[ streamer ] = [ streamer_status, streamer_tag ]

    lock_streamer_status_dict.release()

#================================================

def get_streamer_html_content( streamer ):

    try:
        streamer_html_content = urllib.request.urlopen( 'https://m.twitch.tv/' + streamer, None, REQUEST_TIMEOUT ).read().decode( 'utf-8' )
    except urllib.error.HTTPError as exception:
        if exception.code == 555:
            streamer_html_content = ''
        else:
            raise exception
    except urllib.error.URLError as exception:
        if type( exception.reason ) == TimeoutError:
            streamer_html_content = ''
        else:
            raise exception
    except TimeoutError as exception:
        streamer_html_content = ''
    except Exception as exception:
        raise exception

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
    
        sys.exit( error.errno )
    
    config_file_text = config_file.read()
    
    config_file.close()

    return config_file_text

#================================================

def print_main_output_loop( streamer_status_dict, username_not_valid_list ):

    while( flag_should_stop.is_set() == False ):

        print_main_output( streamer_status_dict, username_not_valid_list )

        time.sleep( ( 1 / REQUEST_PER_SECOND_LIMIT ) / 2 )

#================================================

def print_main_output( streamer_status_dict, username_not_valid_list ):

    if len( streamer_status_dict ) > 0:
        clear_screen()

        lock_streamer_status_dict.acquire()

        streamer_string_length_max = max( map( len, streamer_status_dict.keys() ) )

        for streamer in streamer_status_dict.keys():
            print_streamer_status( streamer, streamer_status_dict[ streamer ][ 0 ].value, streamer_status_dict[ streamer ][ 1 ], streamer_string_length_max )

        lock_streamer_status_dict.release()
    else:
        print_to_stderr( 'No streamer to check, check your configuration file.' )

    for username in username_not_valid_list:
        print_to_stderr( '"' + username + '"' + " does NOT follow the Twitch's username rules." )

#================================================

def print_streamer_status( streamer, streamer_status, streamer_tag, streamer_string_length_max ):
    print( '{}\t'.format( streamer.ljust( streamer_string_length_max ) ), end = '' )
    print( '{}\t'.format( streamer_status.ljust( MAX_STREAMER_STATUS_ENUM_LENGTH ) ), end = '' )

    if streamer_status == StreamerStatus.live.value :
        print( '[' + streamer_tag + ']' )
    else:
        print('')

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

def hook_exception_thread( exception_arg ):

    global exception_thread

    lock_exception_thread.acquire()

    if(exception_thread == None):
        exception_thread = exception_arg.exc_value

        flag_should_stop.set()

    lock_exception_thread.release()

#================================================

def handler_interrupt( signal_number, frame_current ):
    flag_should_stop.set()

#================================================

if __name__ == '__main__':
    main()
