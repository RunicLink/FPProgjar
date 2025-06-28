# client_network.py
import socket
import json
import threading

class BattleshipClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self.game_state = {
            'own_board': None,
            'opponent_board': None,
            'your_turn': False,
            'game_started': False,
            'player_number': None,
            'player_name': '', # Added player name
            'opponent_name': '', # Added opponent name
            'room_code': None, # Added room code
            'is_spectator': False, # Added spectator flag
            'spectate_board_p1': None, # Board for spectator
            'spectate_board_p2': None, # Board for spectator
            'current_turn_player_name': None # Player name whose turn it is
        }
        self.message_callbacks = []

    def connect(self):
        try:
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # Start listening for messages
            listen_thread = threading.Thread(target=self.listen_for_messages)
            listen_thread.daemon = True
            listen_thread.start()
            
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

    def listen_for_messages(self):
        while self.connected:
            try:
                # Increased buffer size to handle larger game state messages
                data = self.socket.recv(4096).decode('utf-8') 
                if not data:
                    break
                
                # Handling multiple JSON objects in one go
                for message_str in data.split('}{'):
                    if not message_str.startswith('{'):
                        message_str = '{' + message_str
                    if not message_str.endswith('}'):
                        message_str = message_str + '}'
                    
                    try:
                        message = json.loads(message_str)
                        self.handle_message(message)
                    except json.JSONDecodeError:
                        print(f"Skipping malformed JSON: {message_str}")
                
            except Exception as e:
                print(f"Error receiving message: {e}")
                break
        
        self.connected = False

    def handle_message(self, message):
        msg_type = message.get('type')
        
        if msg_type == 'game_found':
            self.game_state['player_number'] = message['player_number']
            self.game_state['room_code'] = message.get('room_code')
            self.game_state['player_name'] = message.get('player_name', '')
        elif msg_type == 'game_state':
            # This handles both player and spectator game states
            if not self.game_state['is_spectator']:
                self.game_state['own_board'] = message['own_board']
                self.game_state['opponent_board'] = message['opponent_board']
                self.game_state['your_turn'] = message['your_turn']
                self.game_state['game_started'] = message['game_started']
                self.game_state['player_name'] = message.get('player_name', self.game_state['player_name'])
                self.game_state['opponent_name'] = message.get('opponent_name', self.game_state['opponent_name'])
                self.game_state['current_turn_player_name'] = message.get('current_turn_player_name')
            else: # Spectator mode
                self.game_state['spectate_board_p1'] = message['player1_board']
                self.game_state['spectate_board_p2'] = message['player2_board']
                self.game_state['game_started'] = message['game_started']
                self.game_state['player1_name'] = message.get('player1_name', 'Player 1')
                self.game_state['player2_name'] = message.get('player2_name', 'Player 2')
                self.game_state['current_turn_player_name'] = message.get('current_turn_player_name')

        elif msg_type == 'game_start':
            self.game_state['your_turn'] = message['your_turn']
            self.game_state['game_started'] = True
            self.game_state['player_name'] = message.get('player_name', self.game_state['player_name'])
            self.game_state['opponent_name'] = message.get('opponent_name', '')
            self.game_state['current_turn_player_name'] = message.get('current_turn_player_name')

        elif msg_type == 'attack_result':
            if message['success']:
                self.game_state['your_turn'] = message.get('your_turn', False)
                self.game_state['current_turn_player_name'] = message.get('current_turn_player_name')
        elif msg_type == 'opponent_attack':
            self.game_state['your_turn'] = message.get('your_turn', False)
            self.game_state['current_turn_player_name'] = message.get('current_turn_player_name')

        elif msg_type == 'room_code':
            self.game_state['room_code'] = message['code']
        elif msg_type == 'room_join_status':
            self.game_state['room_join_success'] = message['success']
            self.game_state['message'] = message['message']
        elif msg_type == 'game_list':
            self.game_state['game_list'] = message['games']
        elif msg_type == 'spectate_start':
            self.game_state['is_spectator'] = True
            self.game_state['game_started'] = True
            self.game_state['player1_name'] = message.get('player1_name', 'Player 1')
            self.game_state['player2_name'] = message.get('player2_name', 'Player 2')
            self.game_state['current_turn_player_name'] = message.get('current_turn_player_name')

        # Call registered callbacks
        for callback in self.message_callbacks:
            callback(message)

    def add_message_callback(self, callback):
        self.message_callbacks.append(callback)

    def send_message(self, message):
        if self.connected:
            try:
                self.socket.send(json.dumps(message).encode('utf-8'))
                return True
            except Exception as e:
                print(f"Failed to send message: {e}")
                return False
        return False

    def host_game(self, player_name):
        return self.send_message({'type': 'host_game', 'player_name': player_name})

    def join_private_game(self, player_name, room_code):
        return self.send_message({'type': 'join_private_game', 'player_name': player_name, 'room_code': room_code})

    def quick_play(self):
        return self.send_message({'type': 'quick_play'})

    def get_game_list(self):
        return self.send_message({'type': 'get_game_list'})

    def spectate_game(self, game_id):
        self.game_state['is_spectator'] = True
        return self.send_message({'type': 'spectate_game', 'game_id': game_id})

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

    def get_game_state(self):
        return self.send_message({'type': 'get_game_state'})

    def disconnect(self):
        self.connected = False
        if self.socket:
            self.socket.close()

if __name__ == '__main__':
    # Simple test client
    client = BattleshipClient()
    
    def message_handler(message):
        print(f"Received: {message}")
    
    client.add_message_callback(message_handler)
    
    if client.connect():
        print("Connected to server")
        # Example usage (will be replaced by GUI)
        # client.quick_play()
        
        # Keep the client running
        try:
            while client.connected:
                pass
        except KeyboardInterrupt:
            print("Disconnecting...")
            client.disconnect()
    else:
        print("Failed to connect to server")