# twitch-live-checker

##### Description
###### Check list of streamers if they're live with one command

___
### How to use
```bash
./twitch-live-checker.py
```
The program will read streamers' name from `~/twitch-live-checker.conf`.

##### or
```bash
./twitch-live-checker.py [file]
```
The program will read streamers' name from `[file]` instead.
#### File format
```
[streamer_one's name]
[streamer_two's name]
[streamer_three's name]
          .
          .
          .
```
Just one streamer's name per line. The streamer's name can be found as `https://www.twitch.tv/[streamer's name]`.
