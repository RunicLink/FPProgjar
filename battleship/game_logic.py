import random

class BattleshipGame:
    def __init__(self):
        self.board_size = 10
        self.ships = {
            "Carrier": 5,
            "Battleship": 4,
            "Cruiser": 3,
            "Submarine": 3,
            "Destroyer": 2
        }
        self.player1_board = [['.' for _ in range(self.board_size)] for _ in range(self.board_size)]
        self.player2_board = [['.' for _ in range(self.board_size)] for _ in range(self.board_size)]
        self.player1_ships = {}
        self.player2_ships = {}

    def place_ship(self, player_board, player_ships, ship_name, ship_length, start_row, start_col, orientation):
        # orientation: 'H' for horizontal, 'V' for vertical
        if orientation == 'H':
            if start_col + ship_length > self.board_size:
                return False
            for col in range(start_col, start_col + ship_length):
                if player_board[start_row][col] != '.':
                    return False
            for col in range(start_col, start_col + ship_length):
                player_board[start_row][col] = ship_name[0] # Use first letter of ship name as marker
            player_ships[ship_name] = [(start_row, c) for c in range(start_col, start_col + ship_length)]
        elif orientation == 'V':
            if start_row + ship_length > self.board_size:
                return False
            for row in range(start_row, start_row + ship_length):
                if player_board[row][start_col] != '.':
                    return False
            for row in range(start_row, start_row + ship_length):
                player_board[row][start_col] = ship_name[0]
            player_ships[ship_name] = [(r, start_col) for r in range(start_row, start_row + ship_length)]
        else:
            return False
        return True

    def auto_place_ships(self, player_board, player_ships):
        for ship_name, ship_length in self.ships.items():
            placed = False
            while not placed:
                orientation = random.choice(['H', 'V'])
                if orientation == 'H':
                    start_row = random.randint(0, self.board_size - 1)
                    start_col = random.randint(0, self.board_size - ship_length)
                else:
                    start_row = random.randint(0, self.board_size - ship_length)
                    start_col = random.randint(0, self.board_size - 1)
                placed = self.place_ship(player_board, player_ships, ship_name, ship_length, start_row, start_col, orientation)

    def attack(self, opponent_board, opponent_ships, row, col):
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return "Invalid coordinates"
        if opponent_board[row][col] == 'X' or opponent_board[row][col] == 'O':
            return "Already attacked"

        if opponent_board[row][col] != '.':
            ship_hit_char = opponent_board[row][col]
            ship_name_hit = None
            for name, positions in opponent_ships.items():
                if ship_hit_char == name[0]:
                    ship_name_hit = name
                    break

            opponent_board[row][col] = 'X' # Mark as hit
            
            # Check if ship is sunk
            sunk = True
            for r, c in opponent_ships[ship_name_hit]:
                if opponent_board[r][c] != 'X':
                    sunk = False
                    break
            if sunk:
                return f"Hit and sunk {ship_name_hit}!"
            else:
                return "Hit"
        else:
            opponent_board[row][col] = 'O' # Mark as miss
            return "Miss"

    def check_game_over(self, board, ships):
        """
        Memeriksa apakah semua kapal di papan yang diberikan sudah tenggelam.
        Mengembalikan True jika game berakhir, False jika tidak.
        """
        if not ships:
            return False
            
        for ship_name, positions in ships.items():
            for r, c in positions:
                if board[r][c] != 'X':
                    return False
        return True

    def print_board(self, board):
        for row in board:
            print(" ".join(row))


if __name__ == '__main__':
    game = BattleshipGame()
    game.auto_place_ships(game.player1_board, game.player1_ships)
    game.auto_place_ships(game.player2_board, game.player2_ships)

    print("Player 1 Board:")
    game.print_board(game.player1_board)
    print("\nPlayer 2 Board:")
    game.print_board(game.player2_board)

    # Example attacks
    print("\nAttacking Player 1's board:")
    print(game.attack(game.player1_board, game.player1_ships, 0, 0))
    print(game.attack(game.player1_board, game.player1_ships, 0, 1))
    print(game.attack(game.player1_board, game.player1_ships, 0, 2))
    print(game.attack(game.player1_board, game.player1_ships, 0, 3))
    print(game.attack(game.player1_board, game.player1_ships, 0, 4))
    game.print_board(game.player1_board)

    print("\nAttacking Player 2's board:")
    print(game.attack(game.player2_board, game.player2_ships, 5, 5))
    game.print_board(game.player2_board)

    # Corrected check_game_over logic for testing
    # This part needs to be refined for actual game flow
    all_sunk_player1 = True
    for ship_name, positions in game.player1_ships.items():
        for r, c in positions:
            if game.player1_board[r][c] != 'X':
                all_sunk_player1 = False
                break
        if not all_sunk_player1:
            break
    if all_sunk_player1:
        print("Player 1's ships are all sunk! Game Over.")
    else:
        print("Player 1's ships are not all sunk.")

    all_sunk_player2 = True
    for ship_name, positions in game.player2_ships.items():
        for r, c in positions:
            if game.player2_board[r][c] != 'X':
                all_sunk_player2 = False
                break
        if not all_sunk_player2:
            break
    if all_sunk_player2:
        print("Player 2's ships are all sunk! Game Over.")
    else:
        print("Player 2's ships are not all sunk.")


