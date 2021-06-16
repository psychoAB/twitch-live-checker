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

filepath = pathlib.Path.home() / pathlib.Path( '.twitch-live-checker.conf' )
retry_limit = 3
retry_interval = 0.5
main_thread_interval = 0.2
thread_max = 4

streamer_status = {}

class StreamerStatus( enum.Enum ):
    waiting     = 'Waiting'
    checking    = 'Checking'
    live        = 'Live'
    offline     = 'Offline'
    not_found   = 'Not Found'

#================================================

def main():

    global filepath
    global streamer_status

    if len( sys.argv ) > 1:
        filepath = sys.argv[ 1 ]

    clear_screen()

    file_text = read_streamer_list_file( filepath )
    
    streamer_list = parse_streamer_list_file( file_text )
    
    streamer_max_length = max( map( len, streamer_list ) )

    streamer_status = dict( zip( streamer_list, [ StreamerStatus.waiting ] * len( streamer_list ) ) )

    streamer_list.reverse()

    while ( len( streamer_list ) > 0 ) | ( threading.activeCount() > 1 ):

        while ( len( streamer_list ) > 0 ) & ( threading.activeCount() < thread_max + 1 ):
            threading.Thread( target = check_streamer_status, args = ( streamer_list.pop(), ) ).start()

        for streamer in streamer_status.keys():
            print_streamer_status( streamer, streamer_status[ streamer ].value, streamer_max_length )

        time.sleep( main_thread_interval )

        clear_screen()

    for streamer in streamer_status.keys():
        print_streamer_status( streamer, streamer_status[ streamer ].value, streamer_max_length )

#================================================

def check_streamer_status( streamer ):

    global streamer_status

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

def print_streamer_status( streamer, status, streamer_max_length ):
    print( '{}\t'.format( streamer.ljust( streamer_max_length ) ) + status )

#================================================

def get_streamer_html_content( streamer ):
    try:
        html_content = urllib.request.urlopen( 'https://www.twitch.tv/' + streamer ).read().decode( 'utf-8' )
    except urllib.error.URLError as error:
        if type( error.reason ) == socket.gaierror:
            print_to_stderr( str( error ) )

            print_to_stderr( 'Check your network connection.' )

            quit( error.reason.errno )

    return html_content

#================================================

def parse_streamer_list_file( file_text ):
    streamer_list = file_text.split( '\n' )

    streamer_list = streamer_list[ 0 : -1 ]

    for streamer in streamer_list:
        if re.fullmatch( '[a-zA-Z0-9]\w{3,24}', streamer ) == None:
            streamer_list.remove( streamer )

            print_to_stderr( '"' + streamer + '"' + " does NOT follow the Twitch's username rules." )

    return streamer_list

#================================================

def read_streamer_list_file( filepath ):
    try:
        file = open( filepath, 'r' )
    except FileNotFoundError as error:
        print_to_stderr( str( error ) )
    
        quit( error.errno )
    
    file_text = file.read()
    
    file.close()

    return file_text

#================================================

def clear_screen():
    if os.name == 'nt':
        os.system( 'cls' )
    else:
        os.system( 'clear') 

#================================================

def print_to_stderr( message ):
    print( message, file = sys.stderr )

#================================================

if __name__ == '__main__':
    main()
