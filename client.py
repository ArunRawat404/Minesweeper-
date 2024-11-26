import tkinter as tk
from tkinter import messagebox as tkMessageBox
from collections import deque
import random
import platform
from datetime import datetime, timedelta
import socketio
import threading
import time
import os
import sys

# Ensure Tkinter is working
if not hasattr(tk, 'Tk'):
    print("Tkinter not properly installed. Please reinstall Python with Tkinter support.")
    sys.exit(1)

SIZE_X = 10
SIZE_Y = 10

STATE_DEFAULT = 0
STATE_CLICKED = 1
STATE_FLAGGED = 2

BTN_CLICK = "<Button-1>"
BTN_FLAG = "<Button-2>" if platform.system() == 'Darwin' else "<Button-3>"

class MinesweeperMultiplayer:
    def __init__(self, root):
        # Validate root is a valid Tkinter root window
        if not isinstance(root, tk.Tk):
            raise ValueError("root must be a tk.Tk instance")

        # Socket IO setup
        try:
            self.sio = socketio.Client()
        except Exception as e:
            tkMessageBox.showerror("Socket Error", f"Could not initialize socket: {e}")
            root.quit()
            return

        self.is_game_completed = False

        # Setup socket event listeners
        self.setup_socket_listeners()

        # Import images more robustly
        self.images = {
            "plain": None,
            "clicked": None,
            "mine": None,
            "flag": None,
            "wrong": None,
            "numbers": []
        }

        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Try to load images
        try:
            # Explicitly use tk.PhotoImage on the root window
            self.images["plain"] = tk.PhotoImage(master=root, file=os.path.join(script_dir, "images", "tile_plain.gif"))
            self.images["clicked"] = tk.PhotoImage(master=root, file=os.path.join(script_dir, "images", "tile_clicked.gif"))
            self.images["mine"] = tk.PhotoImage(master=root, file=os.path.join(script_dir, "images", "tile_mine.gif"))
            self.images["flag"] = tk.PhotoImage(master=root, file=os.path.join(script_dir, "images", "tile_flag.gif"))
            self.images["wrong"] = tk.PhotoImage(master=root, file=os.path.join(script_dir, "images", "tile_wrong.gif"))
            
            for i in range(1, 9):
                self.images["numbers"].append(
                    tk.PhotoImage(master=root, file=os.path.join(script_dir, "images", f"tile_{i}.gif"))
                )
        except Exception as e:
            print(f"Error loading images: {e}")
            tkMessageBox.showerror("Image Load Error", 
                                   "Could not load game images. "
                                   "Please ensure 'images' folder exists in the script directory.")
            root.quit()
            return

        # Game state variables
        self.tk = root
        self.frame = tk.Frame(self.tk)
        self.frame.pack()

        self.player_id = None
        self.board_seed = None
        self.game_started = False
        self.start_time = None
        
        # Labels
        self.labels = {
            "time": tk.Label(self.frame, text="00:00:00"),
            "mines": tk.Label(self.frame, text="Mines: 0"),
            "flags": tk.Label(self.frame, text="Flags: 0"),
            "player": tk.Label(self.frame, text="Waiting for players...")
        }
        self.labels["time"].grid(row=0, column=0, columnspan=SIZE_Y)
        self.labels["mines"].grid(row=SIZE_X+1, column=0, columnspan=int(SIZE_Y/2))
        self.labels["flags"].grid(row=SIZE_X+1, column=int(SIZE_Y/2)-1, columnspan=int(SIZE_Y/2))
        self.labels["player"].grid(row=SIZE_X+2, column=0, columnspan=SIZE_Y)

        # Timer thread
        self.timer_thread = None
        self.timer_running = False

        # Connect to server
        self.connect_to_server()

    def setup_socket_listeners(self):
        @self.sio.on('connection_error')
        def on_connection_error(data):
            def show_error():
                tkMessageBox.showerror("Connection Error", data.get('message', 'An unknown error occurred'))
                self.tk.quit()

            self.tk.after(0, show_error)

        @self.sio.on('player_connected')
        def on_player_connected(data):
            def update_player_label():
                try:
                    self.player_id = data['player_id']
                    self.board_seed = data['board_seed']
                    self.labels["player"].config(text=f"You are {self.player_id}")

                    if data['total_players'] == 2:
                        self.labels["player"].config(text=f"Game will start soon...")
                except Exception as e:
                    print(f"Error in player_connected handler: {e}")

            # Ensure update happens on main thread
            if self.tk and hasattr(self.tk, 'after'):
                self.tk.after(0, update_player_label)
            else:
                print("Tkinter root not initialized or after method not available")

        @self.sio.on('game_start')
        def on_game_start(data):
            def start_game():
                try:
                    # Ensure board seed is set from the received data
                    self.board_seed = data.get('board_seed', random.randint(1, 1000000))
                    self.game_started = True
                    self.start_time = datetime.now()
                    self.restart()
                    self.labels["player"].config(text=f"Game started! You are {self.player_id}")
                    
                    # Start timer thread
                    self.timer_running = True
                    self.timer_thread = threading.Thread(target=self.update_timer)
                    self.timer_thread.daemon = True
                    self.timer_thread.start()
                except Exception as e:
                    print(f"Error in game start: {e}")

            # Ensure this runs on the main thread
            if self.tk and hasattr(self.tk, 'after'):
                self.tk.after(0, start_game)
            else:
                print("Tkinter root not initialized or after method not available")

        @self.sio.on('game_over')
        def on_game_over(data):
            def show_game_over():
                try:
                    winner = data['winner']
                    times = data['times']
                    
                    # Stop timer
                    self.timer_running = False
                    
                    msg = f"{winner} won!\n"
                    for player, finish_time in times.items():
                        msg += f"{player}: {finish_time}\n"
                    
                    tkMessageBox.showinfo("Game Over", msg)
                    self.tk.quit()
                except Exception as e:
                    print(f"Error in game over handler: {e}")

            # Ensure game over happens on main thread
            if self.tk and hasattr(self.tk, 'after'):
                self.tk.after(0, show_game_over)
            else:
                print("Tkinter root not initialized or after method not available")

        @self.sio.on('game_completed')
        def on_game_completed(data):
            def show_game_completion():
                try:
                    winner = data['winner']
                    times = data['times']
                    
                    # Stop timer
                    self.timer_running = False
                    self.is_game_completed = True
                    
                    # Disable all buttons
                    for x in range(SIZE_X):
                        for y in range(SIZE_Y):
                            self.tiles[x][y]['button'].config(state=tk.DISABLED)
                    
                    msg = f"{winner} won the game!\n\nGame Times:\n"
                    for player, finish_time in times.items():
                        msg += f"{player}: {finish_time}\n"
                    
                    tkMessageBox.showinfo("Game Completed", msg)
                    self.tk.quit()
                except Exception as e:
                    print(f"Error in game completion handler: {e}")

            # Ensure game completion happens on main thread
            if self.tk and hasattr(self.tk, 'after'):
                self.tk.after(0, show_game_completion)
            else:
                print("Tkinter root not initialized or after method not available")

    def connect_to_server(self):
        try:
            self.sio.connect('http://localhost:5000')
        except Exception as e:
            tkMessageBox.showerror("Connection Error", str(e))
            self.tk.quit()

    def update_timer(self):
        while self.timer_running and self.start_time:
            elapsed = datetime.now() - self.start_time
            timer_str = str(elapsed).split('.')[0]
            
            # Update label in main thread
            self.tk.after(0, lambda t=timer_str: self.labels["time"].config(text=t))
            time.sleep(1)

    def setup(self):
        # Use fixed seed for consistent board
        random.seed(self.board_seed)

        # Rest of the setup remains the same as original code
        self.flagCount = 0
        self.correctFlagCount = 0
        self.clickedCount = 0

        self.tiles = dict({})
        self.mines = 0
        for x in range(0, SIZE_X):
            for y in range(0, SIZE_Y):
                if y == 0:
                    self.tiles[x] = {}

                id = f"{x}_{y}"
                isMine = False

                gfx = self.images["plain"]

                if random.uniform(0.0, 1.0) < 0.1:
                    isMine = True
                    self.mines += 1

                tile = {
                    "id": id,
                    "isMine": isMine,
                    "state": STATE_DEFAULT,
                    "coords": {"x": x, "y": y},
                    "button": tk.Button(self.frame, image=gfx),
                    "mines": 0
                }

                tile["button"].bind(BTN_CLICK, self.onClickWrapper(x, y))
                tile["button"].bind(BTN_FLAG, self.onRightClickWrapper(x, y))
                tile["button"].grid(row=x+1, column=y)

                self.tiles[x][y] = tile

        # Calculate nearby mines
        for x in range(0, SIZE_X):
            for y in range(0, SIZE_Y):
                mc = 0
                for n in self.getNeighbors(x, y):
                    mc += 1 if n["isMine"] else 0
                self.tiles[x][y]["mines"] = mc

        self.refreshLabels()

    def restart(self):
        # Clear existing buttons
        for x in range(SIZE_X):
            for y in range(SIZE_Y):
                if hasattr(self, 'tiles') and x in self.tiles and y in self.tiles[x]:
                    self.tiles[x][y]["button"].destroy()

        # Restore random seed before setup
        random.seed(self.board_seed)
        self.setup()

    def onClick(self, tile):
        # Only allow clicking if game has started and not completed
        if not self.game_started or self.is_game_completed:
            return

        if tile["isMine"] == True:
            return  # No immediate game over in multiplayer

        if tile["mines"] == 0:
            tile["button"].config(image=self.images["clicked"])
            self.clearSurroundingTiles(tile["id"])
        else:
            tile["button"].config(image=self.images["numbers"][tile["mines"]-1])

        if tile["state"] != STATE_CLICKED:
            tile["state"] = STATE_CLICKED
            self.clickedCount += 1

        if self.clickedCount == (SIZE_X * SIZE_Y) - self.mines:
            # Calculate game time
            delta = datetime.now() - self.start_time
            game_time = str(delta).split('.')[0]
            
            # Notify server of completion
            self.sio.emit('player_finished', {
                'player_id': self.player_id,
                'game_time': game_time
            })

    def getNeighbors(self, x, y):
        neighbors = []
        coords = [
            {"x": x-1, "y": y-1}, {"x": x-1, "y": y}, {"x": x-1, "y": y+1},
            {"x": x, "y": y-1}, {"x": x, "y": y+1},
            {"x": x+1, "y": y-1}, {"x": x+1, "y": y}, {"x": x+1, "y": y+1},
        ]
        for n in coords:
            try:
                neighbors.append(self.tiles[n["x"]][n["y"]])
            except KeyError:
                pass
        return neighbors

    def onRightClick(self, tile):
        if not self.game_started or self.is_game_completed:
            return

        if tile["state"] == STATE_DEFAULT:
            tile["button"].config(image=self.images["flag"])
            tile["state"] = STATE_FLAGGED
            tile["button"].unbind(BTN_CLICK)
            if tile["isMine"] == True:
                self.correctFlagCount += 1
            self.flagCount += 1
        elif tile["state"] == STATE_FLAGGED:
            tile["button"].config(image=self.images["plain"])
            tile["state"] = STATE_DEFAULT
            tile["button"].bind(BTN_CLICK, self.onClickWrapper(tile["coords"]["x"], tile["coords"]["y"]))
            if tile["isMine"] == True:
                self.correctFlagCount -= 1
            self.flagCount -= 1

        self.refreshLabels()

    def refreshLabels(self):
        self.labels["flags"].config(text=f"Flags: {self.flagCount}")
        self.labels["mines"].config(text=f"Mines: {self.mines}")

    def onClickWrapper(self, x, y):
        return lambda Button: self.onClick(self.tiles[x][y])

    def onRightClickWrapper(self, x, y):
        return lambda Button: self.onRightClick(self.tiles[x][y])

    def clearTile(self, tile_id):
        # Convert tile_id to x and y coordinates
        x, y = map(int, tile_id.split('_'))
        tile = self.tiles[x][y]

        # Prevent clearing already clicked or flagged tiles
        if tile['state'] == STATE_CLICKED or tile['state'] == STATE_FLAGGED:
            return

        # Mark tile as clicked
        tile['state'] = STATE_CLICKED
        self.clickedCount += 1

        # Update button image
        if tile['isMine']:
            tile['button'].config(image=self.images['mine'])
        elif tile['mines'] > 0:
            tile['button'].config(image=self.images['numbers'][tile['mines'] - 1])
        else:
            tile['button'].config(image=self.images['clicked'])

    def clearSurroundingTiles(self, tile_id):
        # Convert tile_id to x and y coordinates
        x, y = map(int, tile_id.split('_'))
        
        # Use getNeighbors method to find surrounding tiles
        neighbors = self.getNeighbors(x, y)
        
        # Clear each neighboring tile
        for neighbor in neighbors:
            neighbor_id = neighbor['id']
            neighbor_tile = self.tiles[neighbor['coords']['x']][neighbor['coords']['y']]
            
            # Only clear tiles that haven't been clicked or flagged
            if neighbor_tile['state'] == STATE_DEFAULT:
                self.clearTile(neighbor_id)
                
                # If the neighboring tile has no mines, recursively clear its surrounding tiles
                if neighbor_tile['mines'] == 0:
                    self.clearSurroundingTiles(neighbor_id)

def main():
    try:
        # Explicitly create Tk instance
        root = tk.Tk()
        root.title("Multiplayer Minesweeper")
        
        # Additional Tkinter initialization checks
        if not root.winfo_exists():
            print("Could not create Tkinter root window")
            return

        # Create the game
        minesweeper = MinesweeperMultiplayer(root)
        
        # Start the main event loop
        root.mainloop()
    except tk.TclError as e:
        print(f"Tkinter error: {e}")
        print("Ensure Tkinter is correctly installed.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        # Ensure socket is disconnected
        if 'minesweeper' in locals():
            try:
                minesweeper.sio.disconnect()
            except:
                pass

if __name__ == "__main__":
    main()