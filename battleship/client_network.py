# client_network.py
import socket
import json
import threading
import time

class BattleshipClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.game_state = {
            'own_board': None,
            'opponent_board': None,
            'your_turn': False,
            'game_started': False,
            'player_number': None,
            'player_name': '',
            'opponent_name': '',
            'room_code': None,
            'is_spectator': False,
            'spectate_board_p1': None,
            'spectate_board_p2': None,
            'current_turn_player_name': None,
            'turn_time_remaining': None,
            'opponent_connected': True,
        }
        self.message_callbacks = []
        self.is_reconnecting = False

    def connect(self):
        if self.connected:
            return True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            listen_thread = threading.Thread(target=self.listen_for_messages)
            listen_thread.daemon = True
            listen_thread.start()
            
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            self.connected = False
            return False

    def listen_for_messages(self):
        while self.connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    self.handle_disconnect()
                    break
                
                # Handle multiple JSON objects in one recv
                buffer = data.decode('utf-8')
                while buffer:
                    try:
                        message, index = json.JSONDecoder().raw_decode(buffer)
                        self.handle_message(message)
                        buffer = buffer[index:].lstrip()
                    except json.JSONDecodeError:
                        # Incomplete message, try to receive more
                        break

            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                print(f"Connection error: {e}")
                self.handle_disconnect()
                break
            except Exception as e:
                print(f"Error receiving message: {e}")
                self.handle_disconnect()
                break
    
    def handle_disconnect(self):
        if not self.is_reconnecting:
            self.connected = False
            print("Disconnected from server.")
            for callback in self.message_callbacks:
                callback({'type': 'disconnected'})
    
    def handle_message(self, message):
        msg_type = message.get('type')
        
        if msg_type == 'game_state':
            self.game_state.update(message)
        elif msg_type == 'game_start':
            self.game_state.update(message)
        elif msg_type == 'attack_result':
            self.game_state.update(message)
        elif msg_type == 'opponent_attack':
            self.game_state.update(message)
        elif msg_type == 'room_code':
            self.game_state['room_code'] = message['code']
        elif msg_type == 'room_join_status':
            self.game_state['room_join_success'] = message['success']
            self.game_state['message'] = message['message']
        elif msg_type == 'reconnect_success':
            self.is_reconnecting = False
            self.game_state.update(message)
            print("Reconnected successfully.")
        elif msg_type == 'opponent_disconnected_temp':
            self.game_state['opponent_connected'] = False
        elif msg_type == 'opponent_reconnected':
            self.game_state['opponent_connected'] = True

        for callback in self.message_callbacks:
            callback(message)

    def add_message_callback(self, callback):
        self.message_callbacks.append(callback)

    def send_message(self, message):
        if not self.connected:
            print("Not connected, cannot send message.")
            return False
        try:
            self.socket.sendall(json.dumps(message).encode('utf-8'))
            return True
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            print(f"Failed to send message: {e}")
            self.handle_disconnect()
            return False
        return False
    
    def reconnect(self, player_name, room_code):
        if self.connected:
            self.disconnect()

        print("Attempting to reconnect...")
        self.is_reconnecting = True
        time.sleep(1) # Give a moment for the old socket to close
        if self.connect():
            self.send_message({
                'type': 'reconnect', 
                'player_name': player_name, 
                'room_code': room_code
            })
        else:
            self.is_reconnecting = False
            print("Reconnect failed: Could not connect to server.")


    def host_game(self, player_name):
        self.game_state['player_name'] = player_name
        return self.send_message({'type': 'host_game', 'player_name': player_name})

    def join_private_game(self, player_name, room_code):
        self.game_state['player_name'] = player_name
        self.game_state['room_code'] = room_code
        return self.send_message({'type': 'join_private_game', 'player_name': player_name, 'room_code': room_code})

    def place_ships(self, ships_data):
        return self.send_message({
            'type': 'place_ships',
            'ships': ships_data
        })

    def attack(self, row, col):
        return self.send_message({
            'type': 'attack',
            'row': row,
            'col': col
        })

    def disconnect(self):
        self.connected = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except OSError:
                pass # Socket already closed
            self.socket = None

if __name__ == '__main__':
    client = BattleshipClient()
    
    def message_handler(message):
        print(f"Received: {message}")
        if message.get('type') == 'disconnected':
            print("Attempting to reconnect in 5 seconds...")
            time.sleep(5)
            # In a real app, you would get name and room_code from a saved state
            client.reconnect(client.game_state['player_name'], client.game_state['room_code'])

    client.add_message_callback(message_handler)
    
    if client.connect():
        print("Connected to server")
        # Example of hosting a game
        client.host_game("Player CLI")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Disconnecting...")
            client.disconnect()
    else:
        print("Failed to connect to server")