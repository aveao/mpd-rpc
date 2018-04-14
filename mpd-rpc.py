import json
import os
import socket
import struct
import time
import asyncio
from mpd import MPDClient

def find_ipc_pipe():
    matches = []
    for root, dirs, files in os.walk('/run/user/1000'):
        for file in files:
            if 'discord-ipc-' in file:
                matches.append(os.path.join(root, file))
    return sorted(matches)[0]


CLIENT_ID = '402794011368095746'

class RPC:
    def __init__(self, client_id):
        self.client_id = client_id
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    def is_closed(self):
        return self.sock.recv(1024)

    def connect(self):
        try:
            self.sock.connect(find_ipc_pipe())
            self.handshake()
            print('[Rich Presence] Connected.')
        except ConnectionRefusedError:
            # Client closed for good, can't reconnect.
            print('[Rich Presence] Failed to connect.')

    def send(self, op, payload):
        json_payload = json.dumps(payload)
        encoded = struct.pack('<ii', op, len(json_payload)) + json_payload.encode()

        try:
            self.sock.send(encoded)
        except (OSError, BrokenPipeError):
            print('[Rich Presence] Failed to send.')

    def handshake(self):
        self.send(0, {'v': 1, 'client_id': self.client_id})

    def set_activity(self, *, mpdclient, play_state, start, details, state):
        payload = {
            'cmd': 'SET_ACTIVITY',
            'args': {
                'activity': {
                    'assets': {
                        'large_image': 'mpdicon',
                        'large_text': 'Music Player Daemon',
                        'small_image': f'{play_state}b',
                        'small_text': f'v{mpdclient.mpd_version}',
                    },
                    'timestamps': {
                        'start': start,
                    },
                    'details': details,
                    'state': state,
                },
                'pid': os.getpid()
            },
            'nonce': str(time.time())
        }

        self.send(1, payload)


class RichPresence():
    def __init__(self):
        self.rpc = RPC(CLIENT_ID)
        self.rpc.connect()
        self.loop = asyncio.get_event_loop()
        self.mpdclient = MPDClient()
        self.mpdclient.connect("localhost", 6600)
        self.loop.run_until_complete(self.mpd_loop(self))

    async def mpd_loop(self, loop):
        lastsong = ""
        laststate = ""
        await asyncio.sleep(3)
        while True: # TODO: Improve this
            status = self.mpdclient.status()
            if (laststate != status["state"] or "songid" not in status or lastsong != status["songid"]):
                print(f"laststate: '{laststate}', lastsong: '{lastsong}")
                lastsong = status["songid"] if "songid" in status else ""
                laststate = status["state"]
                print(f"newstate: {laststate}, newsong: {lastsong}")
                timestamp = int(time.time())
                currentsong = self.mpdclient.currentsong()
                
                if (laststate == "play" or laststate == "pause") and lastsong != "":
                    sTimestamp = (timestamp - int(status['elapsed'].split('.')[0])) if laststate == "play" else timestamp

                    clean_filename = currentsong["file"].split('/')[-1].split('.')[0]
                    title = currentsong["title"] if "title" in currentsong else clean_filename
                    artist = f' by {currentsong["albumartist"]}' if "albumartist" in currentsong else ""
                    album = f'Album: {currentsong["album"]} ' if "album" in currentsong else ""

                    details = f'{title}{artist}' + (" (paused)" if laststate == "pause" else "") # super hacky
                    state = f'{album}(Playlist: {int(currentsong["pos"]) + 1} of {status["playlistlength"]})'
                    self.rpc.set_activity(mpdclient=self.mpdclient, play_state=laststate, start=sTimestamp, details=details, state=state)
                else:
                    self.rpc.set_activity(mpdclient=self.mpdclient, play_state=laststate, start=timestamp, details="Stopped", state="Nothing is playing")

            await asyncio.sleep(5)

if __name__ == '__main__':
    a = RichPresence()