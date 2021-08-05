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

config_file_path = pathlib.Path.home() / pathlib.Path( '.twitch-live-checker.conf' )
retry_limit = 3
retry_interval = 0.5
main_thread_interval = 0.2
thread_max = 1

is_disconnected = False

class StreamerStatus( enum.Enum ):
    waiting     = 'Waiting'
    checking    = 'Checking'
    live        = 'Live'
    offline     = 'Offline'
    not_found   = 'Not Found'

#================================================

def main():

    global config_file_path

    if len( sys.argv ) > 1:
        config_file_path = sys.argv[ 1 ]

    config_file_text = read_config_file( config_file_path )
    
    ( streamer_list, username_not_valid_list ) = parse_config_file( config_file_text )
    
    streamer_status = dict( zip( streamer_list, [ StreamerStatus.waiting ] * len( streamer_list ) ) )

    streamer_list.reverse()

    while ( len( streamer_list ) > 0 ) or ( threading.activeCount() > 1 ):

        while ( len( streamer_list ) > 0 ) and ( threading.activeCount() < thread_max + 1 ):
            threading.Thread( target = check_streamer_status, args = ( streamer_list.pop(), streamer_status ) ).start()

        print_main_output( streamer_status, username_not_valid_list )

        time.sleep( main_thread_interval )

    if is_disconnected == False:
        print_main_output( streamer_status, username_not_valid_list )

#================================================

def check_streamer_status( streamer, streamer_status ):
    should_retry = True
    retry_count = 0

    streamer_status[ streamer ] = StreamerStatus.checking

    while should_retry == True and retry_count < retry_limit:

        html_content = get_streamer_html_content( streamer )

        if html_content.find( 'isLiveBroadcast' ) != -1:
            streamer_status[ streamer ] = StreamerStatus.live

            should_retry = False
        else:
            if html_content.find( streamer ) != -1:
                streamer_status[ streamer ] = StreamerStatus.offline

                should_retry = False
            else:
                retry_count = retry_count + 1

                time.sleep( retry_interval )

    if retry_count >= retry_limit:
        streamer_status[ streamer ] = StreamerStatus.not_found

#================================================

def get_streamer_html_content( streamer ):

    global is_disconnected

    try:
        html_content = urllib.request.urlopen( 'https://www.twitch.tv/' + streamer ).read().decode( 'utf-8' )
    except urllib.error.URLError as error:
        if type( error.reason ) == socket.gaierror:
            if is_disconnected == False:
                is_disconnected = True

                print_to_stderr( str( error ) )

                print_to_stderr( 'Check your network connection.' )

            quit( error.reason.errno )

    return html_content

#================================================

def parse_config_file( config_file_text ):

    global thread_max

    config_file_text_line = config_file_text.split( '\n' )

    config_file_text_line = list( filter( lambda line : line != '', config_file_text_line ) )

    if len( config_file_text_line ) > 0:
        if re.fullmatch( '[1-9][0-9]*', config_file_text_line[ 0 ] ) != None:
            thread_max = int( config_file_text_line[ 0 ] )

            config_file_text_line = config_file_text_line[ 1 : ]

    username_not_valid_list = list( filter( lambda line : re.fullmatch( '[a-zA-Z0-9]\w{3,24}', line ) == None , config_file_text_line ) )
    streamer_list = list( filter( lambda line : line not in username_not_valid_list , config_file_text_line ) )

    return ( streamer_list, username_not_valid_list )

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

def print_main_output( streamer_status, username_not_valid_list ):
    if len( streamer_status ) > 0:
        clear_screen()

        streamer_max_length = max( map( len, streamer_status.keys() ) )

        for streamer in streamer_status.keys():
            print_streamer_status( streamer, streamer_status[ streamer ].value, streamer_max_length )
    else:
        print_to_stderr( 'The streamers list is empty.' )

    for username in username_not_valid_list:
        print_to_stderr( '"' + username + '"' + " does NOT follow the Twitch's username rules." )

#================================================

def print_streamer_status( streamer, status, streamer_max_length ):
    print( '{}\t'.format( streamer.ljust( streamer_max_length ) ) + status )

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
