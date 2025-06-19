import pygame
import sys
import json
from client_network import BattleshipClient

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
BOARD_SIZE = 10
CELL_SIZE = 40
BOARD_MARGIN = 50
SHIP_COLORS = {
    'C': (255, 0, 0),    # Carrier - Red
    'B': (0, 255, 0),    # Battleship - Green
    'R': (0, 0, 255),    # Cruiser - Blue
    'S': (255, 255, 0),  # Submarine - Yellow
    'D': (255, 0, 255)   # Destroyer - Magenta
}

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (0, 100, 200)
RED = (200, 0, 0)
GREEN = (0, 200, 0)
GRAY = (128, 128, 128)
LIGHT_GRAY = (200, 200, 200)
DARK_GRAY = (64, 64, 64)

class BattleshipGUI:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Battleship Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.big_font = pygame.font.Font(None, 36)
        
        # Game state
        self.client = BattleshipClient()
        self.client.add_message_callback(self.handle_server_message)
        
        self.game_phase = "connecting"  # connecting, waiting, placing_ships, playing, game_over
        self.own_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.opponent_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.your_turn = False
        self.player_number = None
        self.status_message = "Connecting to server..."
        
        # Ship placement
        self.ships_to_place = [
            {"name": "Carrier", "length": 5, "placed": False},
            {"name": "Battleship", "length": 4, "placed": False},
            {"name": "Cruiser", "length": 3, "placed": False},
            {"name": "Submarine", "length": 3, "placed": False},
            {"name": "Destroyer", "length": 2, "placed": False}
        ]
        self.current_ship_index = 0
        self.ship_orientation = 'H'  # H for horizontal, V for vertical
        self.placed_ships = []
        
        # Board positions
        self.own_board_rect = pygame.Rect(BOARD_MARGIN, BOARD_MARGIN + 100, 
                                         BOARD_SIZE * CELL_SIZE, BOARD_SIZE * CELL_SIZE)
        self.opponent_board_rect = pygame.Rect(WINDOW_WIDTH - BOARD_MARGIN - BOARD_SIZE * CELL_SIZE, 
                                              BOARD_MARGIN + 100,
                                              BOARD_SIZE * CELL_SIZE, BOARD_SIZE * CELL_SIZE)

    def handle_server_message(self, message):
        msg_type = message.get('type')
        
        if msg_type == 'waiting':
            self.game_phase = "waiting"
            self.status_message = message['message']
        elif msg_type == 'game_found':
            self.game_phase = "placing_ships"
            self.player_number = message['player_number']
            self.status_message = f"You are Player {self.player_number}. Place your ships!"
        elif msg_type == 'ships_placed':
            if message['success']:
                self.status_message = "Ships placed! Waiting for opponent..."
            else:
                self.status_message = message['message']
        elif msg_type == 'game_start':
            self.game_phase = "playing"
            self.your_turn = message['your_turn']
            self.status_message = message['message']
        elif msg_type == 'game_state':
            self.own_board = message['own_board']
            self.opponent_board = message['opponent_board']
            self.your_turn = message['your_turn']
        elif msg_type == 'attack_result':
            if message['success']:
                self.status_message = f"Attack result: {message['result']}"
                self.your_turn = message.get('your_turn', False)
                if message.get('game_over'):
                    self.game_phase = "game_over"
                    self.status_message = "You won!"
            else:
                self.status_message = message['message']
        elif msg_type == 'opponent_attack':
            self.status_message = f"Opponent attacked: {message['result']}"
            self.your_turn = message.get('your_turn', False)
            if message.get('game_over'):
                self.game_phase = "game_over"
                self.status_message = "You lost!"
        elif msg_type == 'game_over':
            self.game_phase = "game_over"
            winner = message['winner']
            if (winner == "Player 1" and self.player_number == 1) or \
               (winner == "Player 2" and self.player_number == 2):
                self.status_message = "You won!"
            else:
                self.status_message = "You lost!"
        elif msg_type == 'opponent_disconnected':
            self.status_message = message['message']

    def connect_to_server(self):
        if self.client.connect():
            self.client.join_game()
            self.game_phase = "waiting"
            self.status_message = "Connected! Waiting for game..."
        else:
            self.status_message = "Failed to connect to server"

    def draw_board(self, board, board_rect, title, clickable=False):
        # Draw title
        title_surface = self.big_font.render(title, True, BLACK)
        title_rect = title_surface.get_rect()
        title_rect.centerx = board_rect.centerx
        title_rect.bottom = board_rect.top - 10
        self.screen.blit(title_surface, title_rect)
        
        # Draw grid
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                cell_rect = pygame.Rect(
                    board_rect.x + col * CELL_SIZE,
                    board_rect.y + row * CELL_SIZE,
                    CELL_SIZE,
                    CELL_SIZE
                )
                
                # Determine cell color
                cell_value = board[row][col]
                if cell_value == '.':
                    color = WHITE
                elif cell_value == 'X':
                    color = RED
                elif cell_value == 'O':
                    color = BLUE
                else:
                    # Ship cell
                    color = SHIP_COLORS.get(cell_value, GRAY)
                
                pygame.draw.rect(self.screen, color, cell_rect)
                pygame.draw.rect(self.screen, BLACK, cell_rect, 1)
                
                # Draw coordinates
                if row == 0:
                    coord_text = self.font.render(str(col), True, BLACK)
                    coord_rect = coord_text.get_rect()
                    coord_rect.centerx = cell_rect.centerx
                    coord_rect.bottom = cell_rect.top - 5
                    self.screen.blit(coord_text, coord_rect)
                
                if col == 0:
                    coord_text = self.font.render(str(row), True, BLACK)
                    coord_rect = coord_text.get_rect()
                    coord_rect.centery = cell_rect.centery
                    coord_rect.right = cell_rect.left - 5
                    self.screen.blit(coord_text, coord_rect)

    def draw_ship_placement_preview(self, mouse_pos):
        if self.current_ship_index >= len(self.ships_to_place):
            return
        
        ship = self.ships_to_place[self.current_ship_index]
        if ship['placed']:
            return
        
        # Convert mouse position to board coordinates
        if self.own_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.own_board_rect.x
            rel_y = mouse_pos[1] - self.own_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                # Check if ship can be placed
                can_place = True
                cells_to_highlight = []
                
                if self.ship_orientation == 'H':
                    if col + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for c in range(col, col + ship['length']):
                            if self.own_board[row][c] != '.':
                                can_place = False
                            cells_to_highlight.append((row, c))
                else:  # Vertical
                    if row + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for r in range(row, row + ship['length']):
                            if self.own_board[r][col] != '.':
                                can_place = False
                            cells_to_highlight.append((r, col))
                
                # Draw preview
                color = GREEN if can_place else RED
                for r, c in cells_to_highlight:
                    cell_rect = pygame.Rect(
                        self.own_board_rect.x + c * CELL_SIZE,
                        self.own_board_rect.y + r * CELL_SIZE,
                        CELL_SIZE,
                        CELL_SIZE
                    )
                    pygame.draw.rect(self.screen, color, cell_rect, 3)

    def place_ship(self, mouse_pos):
        if self.current_ship_index >= len(self.ships_to_place):
            return
        
        ship = self.ships_to_place[self.current_ship_index]
        if ship['placed']:
            return
        
        # Convert mouse position to board coordinates
        if self.own_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.own_board_rect.x
            rel_y = mouse_pos[1] - self.own_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                # Check if ship can be placed
                can_place = True
                cells_to_place = []
                
                if self.ship_orientation == 'H':
                    if col + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for c in range(col, col + ship['length']):
                            if self.own_board[row][c] != '.':
                                can_place = False
                            cells_to_place.append((row, c))
                else:  # Vertical
                    if row + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for r in range(row, row + ship['length']):
                            if self.own_board[r][col] != '.':
                                can_place = False
                            cells_to_place.append((r, col))
                
                if can_place:
                    # Place the ship
                    ship_char = ship['name'][0]
                    for r, c in cells_to_place:
                        self.own_board[r][c] = ship_char
                    
                    ship['placed'] = True
                    self.placed_ships.append({
                        'name': ship['name'],
                        'start_row': row if self.ship_orientation == 'V' else row,
                        'start_col': col if self.ship_orientation == 'H' else col,
                        'orientation': self.ship_orientation
                    })
                    
                    # Move to next ship
                    self.current_ship_index += 1
                    
                    # Check if all ships are placed
                    if self.current_ship_index >= len(self.ships_to_place):
                        self.client.place_ships(self.placed_ships)
                        self.status_message = "All ships placed! Waiting for opponent..."

    def attack_opponent(self, mouse_pos):
        if not self.your_turn or self.game_phase != "playing":
            return
        
        # Convert mouse position to board coordinates
        if self.opponent_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.opponent_board_rect.x
            rel_y = mouse_pos[1] - self.opponent_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                # Check if cell was already attacked
                if self.opponent_board[row][col] in ['.']:
                    self.client.attack(row, col)

    def draw_ship_list(self):
        y_offset = 50
        for i, ship in enumerate(self.ships_to_place):
            color = GREEN if ship['placed'] else (RED if i == self.current_ship_index else BLACK)
            text = f"{ship['name']} ({ship['length']})"
            if i == self.current_ship_index and not ship['placed']:
                text += f" - {self.ship_orientation}"
            
            ship_surface = self.font.render(text, True, color)
            self.screen.blit(ship_surface, (WINDOW_WIDTH // 2 - 100, y_offset + i * 30))

    def draw_status(self):
        # Status message
        status_surface = self.big_font.render(self.status_message, True, BLACK)
        status_rect = status_surface.get_rect()
        status_rect.centerx = WINDOW_WIDTH // 2
        status_rect.y = 10
        self.screen.blit(status_surface, status_rect)
        
        # Turn indicator
        if self.game_phase == "playing":
            turn_text = "Your Turn" if self.your_turn else "Opponent's Turn"
            turn_color = GREEN if self.your_turn else RED
            turn_surface = self.font.render(turn_text, True, turn_color)
            turn_rect = turn_surface.get_rect()
            turn_rect.centerx = WINDOW_WIDTH // 2
            turn_rect.y = 50
            self.screen.blit(turn_surface, turn_rect)

    def run(self):
        self.connect_to_server()
        
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r and self.game_phase == "placing_ships":
                        # Rotate ship orientation
                        self.ship_orientation = 'V' if self.ship_orientation == 'H' else 'H'
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        if self.game_phase == "placing_ships":
                            self.place_ship(event.pos)
                        elif self.game_phase == "playing":
                            self.attack_opponent(event.pos)
            
            # Clear screen
            self.screen.fill(WHITE)
            
            # Draw UI based on game phase
            if self.game_phase in ["waiting", "connecting"]:
                self.draw_status()
            elif self.game_phase == "placing_ships":
                self.draw_status()
                self.draw_board(self.own_board, self.own_board_rect, "Your Board")
                self.draw_ship_list()
                self.draw_ship_placement_preview(pygame.mouse.get_pos())
                
                # Instructions
                instruction_text = "Click to place ship, R to rotate"
                instruction_surface = self.font.render(instruction_text, True, BLACK)
                self.screen.blit(instruction_surface, (10, WINDOW_HEIGHT - 30))
            elif self.game_phase in ["playing", "game_over"]:
                self.draw_status()
                self.draw_board(self.own_board, self.own_board_rect, "Your Board")
                self.draw_board(self.opponent_board, self.opponent_board_rect, "Opponent's Board", True)
                
                # Instructions
                if self.game_phase == "playing":
                    instruction_text = "Click on opponent's board to attack"
                    instruction_surface = self.font.render(instruction_text, True, BLACK)
                    self.screen.blit(instruction_surface, (10, WINDOW_HEIGHT - 30))
            
            pygame.display.flip()
            self.clock.tick(60)
        
        self.client.disconnect()
        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    game = BattleshipGUI()
    game.run()

