#!/bin/env python
import urllib.request
import sys
import socket
import time

from pathlib import Path

#================================================

filepath = Path.home() / Path( '.twitch-live-checker.conf' )
retry_limit = 5
retry_interval = 0.2

#================================================

def main():

    global filepath;

    if len( sys.argv ) > 1:
        filepath = sys.argv[ 1 ]

    file_text = read_streamer_list_file( filepath )
    
    streamer_list = parse_streamer_list_file( file_text )
    
    streamer_max_length = max( map( len, streamer_list ) )
    
    for streamer in streamer_list:
    
        should_retry = True;
        retry_count = 0
    
        while should_retry == True and retry_count < retry_limit:
    
            html_content = get_streamer_html_content( streamer )
    
            if html_content.find( 'isLiveBroadcast' ) != -1:
                print_streamer_status( streamer, 'Live', streamer_max_length )
    
                should_retry = False
            else:
                if html_content.find( streamer ) != -1:
                    print_streamer_status( streamer, 'Offline', streamer_max_length )
    
                    should_retry = False
                else:
                    retry_count = retry_count + 1

                    time.sleep( retry_interval )
    
        if retry_count >= retry_limit:
            print_streamer_status( streamer, 'Not Found', streamer_max_length )

#================================================

def print_streamer_status( streamer, status, streamer_max_length ):
    print( '{}\t'.format( streamer.ljust( streamer_max_length ) ) + status )

#================================================

def get_streamer_html_content( streamer ):
    try:
        html_content = urllib.request.urlopen( 'https://www.twitch.tv/' + streamer ).read().decode( 'utf-8' )
    except urllib.error.URLError as error:
        if type( error.reason ) == socket.gaierror:
            print( str( error.reason ) )

            print( 'Check your network connection.' )

            quit( error.reason.errno )
        else:
            print( str( error.reason ) )

            print( "It's unexpected." )

            quit( error.errno )
    except Exception as error:
        print( str( error ) )

        print( "It's unexpected." )

        quit( error.errno )

    return html_content

#================================================

def parse_streamer_list_file( file_text ):
    streamer_list = file_text.split( '\n' )

    streamer_list = streamer_list[ 0 : -1 ]

    return streamer_list

#================================================

def read_streamer_list_file( filepath ):
    try:
        file = open( filepath, 'r' )
    except FileNotFoundError as error:
        print( str( error ) )
    
        quit( error.errno )
    except Exception as error:
        print( str( error ) )
    
        print( "It's unexpected." )
    
        quit( error.errno )
    
    file_text = file.read()
    
    file.close()

    return file_text

#================================================

if __name__ == '__main__':
    main()
