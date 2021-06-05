#!/bin/env python
import urllib.request
import sys
import socket

#================================================

filepath = 'streamer_list.txt'
retry_limit = 5

#================================================

if len( sys.argv ) > 1:
    filepath = sys.argv[ 1 ]

#================================================

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

#================================================

streamer_list = file_text.split( '\n' )

streamer_list = streamer_list[ 0 : -1 ]

#================================================

streamer_max_length = max( map( len, streamer_list ) )

#================================================

for streamer in streamer_list:

    should_retry = True;
    retry_count = 0

    while should_retry == True and retry_count < retry_limit:

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

        if html_content.find( 'isLiveBroadcast' ) != -1:
            print( '{}\tLive'.format( streamer.ljust( streamer_max_length ) ) )

            should_retry = False
        else:
            if html_content.find( streamer ) != -1:
                print( '{}\tOffline'.format( streamer.ljust( streamer_max_length ) ) )

                should_retry = False
            else:
                retry_count = retry_count + 1

    if retry_count >= retry_limit:
        print( '{}\tNot Found'.format( streamer.ljust( streamer_max_length ) ) )
