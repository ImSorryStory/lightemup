import os
import time
import random
import json

from flask import Flask, request, session, redirect, url_for, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

##################################
# ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ FLASK
##################################

app = Flask(__name__)
app.secret_key = "some_secret_for_sessions"

# Настраиваем базу данных SQLite
db_path = os.path.join(os.path.dirname(__file__), 'lightemup.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------------------------------------------
# МОДЕЛИ ДАННЫХ
# -------------------------------------------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    nickname = db.Column(db.String(50), unique=True, nullable=False)
    avatar = db.Column(db.String(250), default="")
    best_score = db.Column(db.Integer, default=0)

class ScoreEvent(db.Model):
    __tablename__ = 'score_events'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    score = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.Float, default=time.time)

with app.app_context():
    db.create_all()

# -------------------------------------------------------
# ОПОВЕЩЕНИЯ
# -------------------------------------------------------
announcement = None
def set_announcement(msg, nickname, avatar, score):
    global announcement
    announcement = {
        "message": msg,
        "timestamp": time.time(),
        "avatar": avatar,
        "nickname": nickname,
        "score": score
    }

# -------------------------------------------------------
# ЛИДЕРБОРД
# -------------------------------------------------------
def get_global_top1_score():
    top_user = User.query.order_by(User.best_score.desc()).first()
    return (top_user.nickname, top_user.best_score) if top_user else (None, 0)

def update_leaderboard_if_needed(user_obj, new_score):
    old_top_nick, old_top_score = get_global_top1_score()
    if new_score > old_top_score:
        user_obj.best_score = new_score
        db.session.commit()
        set_announcement("Новый лидер!", user_obj.nickname, user_obj.avatar, new_score)
        return True
    return False

# -------------------------------------------------------
# ПАЗЛ: BLOCK, PUZZLE
# -------------------------------------------------------
class Block:
    def __init__(self, block_type, orientation=0):
        self.block_type = block_type
        self.orientation = orientation

    def rotate(self):
        self.orientation = (self.orientation + 1) % 4

    def to_dict(self):
        return {"type": self.block_type, "orientation": self.orientation}

class Puzzle:
    def __init__(self, size, blocks):
        self.size = size
        self.blocks = blocks

    def to_json_data(self):
        return {
            "size": self.size,
            "blocks": [[b.to_dict() for b in row] for row in self.blocks]
        }

# -------------------------------------------------------
# EASY: горизонтальная змейка
# -------------------------------------------------------
def generate_easy_snake_path(size):
    path=[]
    for y in range(size):
        row=[(y,x) for x in range(size)]
        if y%2==1:
            row.reverse()
        path.extend(row)
    return path

def generate_column_snake_path(size):
    path=[]
    for x in range(size):
        col=[(y,x) for y in range(size)]
        if x%2==1:
            col.reverse()
        path.extend(col)
    return path

# -------------------------------------------------------
# MEDIUM: улитка
# -------------------------------------------------------
def generate_snail_path(size):
    path=[]
    left,right=0,size-1
    top,bottom=0,size-1
    while left<=right and top<=bottom:
        for x in range(left,right+1):
            path.append((top,x))
        top+=1
        for y in range(top,bottom+1):
            path.append((y,right))
        right-=1
        if top<=bottom:
            for x in range(right,left-1,-1):
                path.append((bottom,x))
            bottom-=1
        if left<=right:
            for y in range(bottom,top-1,-1):
                path.append((y,left))
            left+=1
    return path

# -------------------------------------------------------
# ПРОВЕРКА "ОБЫЧНОЙ" ЗМЕЙКИ
# -------------------------------------------------------
def is_basic_snake(path, size):
    if path==generate_easy_snake_path(size):
        return True
    if path==generate_column_snake_path(size):
        return True
    return False

# -------------------------------------------------------
# ФУНКЦИИ ДЛЯ ОБРАБОТКИ ПУТЕЙ
# -------------------------------------------------------
def is_chain_path(path, size):
    n=len(path)
    if n!=size*size:
        return False
    used=set(path)
    if len(used)!=n:
        return False
    for i in range(n-1):
        (y1,x1)=path[i]
        (y2,x2)=path[i+1]
        if abs(y1-y2)+abs(x1-x2)!=1:
            return False
    return True

def attempt_2opt(path):
    n=len(path)
    if n<5:
        return path
    i=random.randint(1,n-3)
    j=random.randint(i+1,n-2)
    new_path=path[:i]+list(reversed(path[i:j+1]))+path[j+1:]
    if is_chain_path(new_path, int(n**0.5)):
        return new_path
    return path

def attempt_segment_relocate(path):
    n=len(path)
    if n<5:
        return path
    seg_len=random.randint(2, min(8,n-2))
    start_i=random.randint(1,n-seg_len-1)
    segment=path[start_i:start_i+seg_len]
    remain=path[:start_i]+path[start_i+seg_len:]
    for _ in range(30):
        pos=random.randint(1,len(remain)-1)
        candidate=remain[:pos]+segment+remain[pos:]
        if is_chain_path(candidate,int(n**0.5)):
            return candidate
    return path

def local_improve_path(path, size, iterations=15):
    if not is_chain_path(path,size):
        return path
    best=path[:]
    for _ in range(iterations):
        if random.random()<0.5:
            candidate=attempt_2opt(best)
        else:
            candidate=attempt_segment_relocate(best)
        if candidate!=best:
            best=candidate
    return best

# -------------------------------------------------------
# 1) Maze-based
# -------------------------------------------------------
def generate_path_maze_based(size):
    print(f"[MazeBased] size={size}, без ограничений по времени. (DFS-лабиринт)")
    # Генерируем лабиринт + Backtracking поиск пути
    visited=[[False]*size for _ in range(size)]
    edges={}
    for y in range(size):
        for x in range(size):
            edges[(y,x)]=[]
    def maze_dfs(cy,cx):
        visited[cy][cx]=True
        dirs=[(-1,0),(1,0),(0,-1),(0,1)]
        random.shuffle(dirs)
        for (dy,dx) in dirs:
            ny,nx=cy+dy,cx+dx
            if 0<=ny<size and 0<=nx<size and not visited[ny][nx]:
                edges[(cy,cx)].append((ny,nx))
                edges[(ny,nx)].append((cy,cx))
                maze_dfs(ny,nx)
    # Рандомный старт для генерации лабиринта
    sy,sx=random.randint(0,size-1), random.randint(0,size-1)
    maze_dfs(sy,sx)

    path=[]
    visited2=set()
    total=size*size

    def unify_dfs(cy,cx):
        visited2.add((cy,cx))
        path.append((cy,cx))
        if len(path)==total:
            return True
        nbr=edges[(cy,cx)]
        random.shuffle(nbr)
        for (ny,nx) in nbr:
            if (ny,nx) not in visited2:
                if unify_dfs(ny,nx):
                    return True
        visited2.remove((cy,cx))
        path.pop()
        return False

    # Запустим unify с другой случайной точки
    sy2,sx2=random.randint(0,size-1), random.randint(0,size-1)
    ok=unify_dfs(sy2,sx2)
    if ok and len(path)==total:
        path=local_improve_path(path,size,iterations=15)
        if is_chain_path(path,size):
            return path
    return None

# -------------------------------------------------------
# 2) Hilbert
# -------------------------------------------------------
def is_power_of_two(n):
    return (n&(n-1))==0

def hilbert_d_to_xy(n,d):
    x=y=0
    s=1
    t=d
    while s<n:
        rx=1&(t//2)
        ry=1&(t^rx)
        if ry==0:
            if rx==1:
                x=s-1-x
                y=s-1-y
            x,y=y,x
        x+=s*rx
        y+=s*ry
        t//=4
        s<<=1
    return (x,y)

def generate_path_hilbert(size):
    if not is_power_of_two(size):
        return None
    print(f"[Hilbert] size={size}, без лимита.")
    total=size*size
    path=[]
    for d in range(total):
        (xx,yy)=hilbert_d_to_xy(size,d)
        path.append((yy,xx))
    path=local_improve_path(path,size,iterations=15)
    if is_chain_path(path,size):
        return path
    return None

# -------------------------------------------------------
# 3) Sierpinski
# -------------------------------------------------------
def generate_path_sierpinski(size):
    if not is_power_of_two(size):
        return None
    print(f"[Sierpinski] size={size}.")
    path=[]
    total=size*size
    def rotate90(r,c,n):
        return (c,n-1-r)
    def sierpinski_curve(y0,x0,s,orient=0):
        if s==2:
            base=[(0,0),(0,1),(1,1),(1,0)]
            cur=base[:]
            for _ in range(orient%4):
                cur=[rotate90(rr,cc,2) for (rr,cc) in cur]
            for (rr,cc) in cur:
                path.append((y0+rr,x0+cc))
            return
        half=s//2
        sierpinski_curve(y0+half,x0,half,(orient+1)%4)
        sierpinski_curve(y0,x0,half,orient)
        sierpinski_curve(y0,x0+half,half,orient)
        sierpinski_curve(y0+half,x0+half,half,(orient-1)%4)
    sierpinski_curve(0,0,size,0)
    if len(path)==total:
        path=local_improve_path(path,size,iterations=15)
        if is_chain_path(path,size):
            return path
    return None

# -------------------------------------------------------
# 4) Улучшенный Warnsdorff
# -------------------------------------------------------
def generate_path_warnsdorff_improved(size, start_attempts=8, local_backtrack_depth=3):
    print(f"[Warnsdorff+] size={size}, attempts={start_attempts}, no time limit.")
    total=size*size
    def count_unvisited_neighbors(y,x, visited):
        c=0
        for (dy,dx) in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny,nx=y+dy,x+dx
            if 0<=ny<size and 0<=nx<size and not visited[ny][nx]:
                c+=1
        return c
    def cell_score(y,x, visited):
        # 2-ходовый look-ahead
        sc=count_unvisited_neighbors(y,x, visited)
        min2=999999
        for (dy,dx) in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny,nx=y+dy,x+dx
            if 0<=ny<size and 0<=nx<size and not visited[ny][nx]:
                c2=count_unvisited_neighbors(ny,nx,visited)
                if c2<min2: min2=c2
        if min2==999999:
            min2=0
        return sc+min2
    def local_backtrack(path, visited, steps):
        for _ in range(steps):
            if not path:
                break
            (py,px)=path.pop()
            visited[py][px]=False
    def single_attempt(sy,sx):
        visited=[[False]*size for _ in range(size)]
        path=[(sy,sx)]
        visited[sy][sx]=True
        while len(path)<total:
            (cy,cx)=path[-1]
            candidates=[]
            for (dy,dx) in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny,nx=cy+dy,cx+dx
                if 0<=ny<size and 0<=nx<size and not visited[ny][nx]:
                    sc=cell_score(ny,nx,visited)
                    candidates.append((sc,ny,nx))
            if not candidates:
                # лок откат
                for depth in range(1,local_backtrack_depth+1):
                    if len(path)<=depth:
                        return None
                    local_backtrack(path,visited,depth)
                if len(path)<total:
                    # попробуем продолжить, но если path не растёт, скорее всего None
                    if len(path)==0:
                        return None
            else:
                candidates.sort(key=lambda x:x[0])
                best=candidates[0][0]
                eq=[c for c in candidates if c[0]==best]
                (_, ty, tx)=random.choice(eq)
                visited[ty][tx]=True
                path.append((ty,tx))
        return path

    for attempt_i in range(1,start_attempts+1):
        sy,sx=random.randint(0,size-1), random.randint(0,size-1)
        p=single_attempt(sy,sx)
        if p and len(p)==total:
            p=local_improve_path(p,size,iterations=15)
            if is_chain_path(p,size):
                return p
    return None

# -------------------------------------------------------
# 5) Backtracking DFS (удалён fallback easy snake)
# -------------------------------------------------------
def generate_path_backtracking_dfs(size, max_attempts=10):
    """
    Полный бэктрекинг без строгого time_limit (или очень большой limit).
    """
    print(f"[BacktrackingDFS] size={size}, max_attempts={max_attempts}, no fallback snake.")
    total=size*size

    def single_try():
        visited=[[False]*size for _ in range(size)]
        path=[]
        sy,sx=random.randint(0,size-1), random.randint(0,size-1)

        def neighbors(y,x):
            dirs=[(-1,0),(1,0),(0,-1),(0,1)]
            random.shuffle(dirs)
            for (dy,dx) in dirs:
                ny,nx=y+dy,x+dx
                if 0<=ny<size and 0<=nx<size and not visited[ny][nx]:
                    yield (ny,nx)

        def backtrack(cy,cx):
            visited[cy][cx]=True
            path.append((cy,cx))
            if len(path)==total:
                return True
            for (ny,nx) in neighbors(cy,cx):
                if not visited[ny][nx]:
                    if backtrack(ny,nx):
                        return True
            visited[cy][cx]=False
            path.pop()
            return False

        if backtrack(sy,sx):
            return path
        return None

    for attempt_i in range(1,max_attempts+1):
        p=single_try()
        if p and len(p)==total:
            p=local_improve_path(p,size,iterations=15)
            if is_chain_path(p,size):
                return p
    return None

# -------------------------------------------------------
# 6) Forceful BFS (для полей <=20)
# -------------------------------------------------------
def generate_path_forceful_bfs(size):
    """
    Полная BFS/DFS поиска гамильтонова пути,
    без таймлимита, но с жёсткими эвристиками,
    чтобы не «висеть» бесконечно.
    """
    print(f"[ForcefulBFS] size={size}. Полный поиск гамильтонова пути.")
    if size>20:
        return None  # не применяем на больших

    total=size*size
    visited=[[False]*size for _ in range(size)]
    path=[]

    # Сортируем соседей по количеству ещё не посещённых соседей (Warnsdorff-like).
    def neighbors(y,x):
        nbr=[]
        for (dy,dx) in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny,nx=y+dy,x+dx
            if 0<=ny<size and 0<=nx<size and not visited[ny][nx]:
                # счёт
                c=0
                for (dy2,dx2) in [(-1,0),(1,0),(0,-1),(0,1)]:
                    my,mx=ny+dy2,nx+dx2
                    if 0<=my<size and 0<=mx<size and not visited[my][mx]:
                        c+=1
                nbr.append((c,ny,nx))
        nbr.sort(key=lambda x:x[0])  # Warnsdorff
        return [(ny,nx) for (c,ny,nx) in nbr]

    def backtrack(cy,cx):
        visited[cy][cx]=True
        path.append((cy,cx))
        if len(path)==total:
            return True
        nbs=neighbors(cy,cx)
        for (ny,nx) in nbs:
            if not visited[ny][nx]:
                if backtrack(ny,nx):
                    return True
        visited[cy][cx]=False
        path.pop()
        return False

    # Пробуем со случайных стартовых клеток
    start_list=[]
    for _ in range(5):
        sy,sx=random.randint(0,size-1), random.randint(0,size-1)
        start_list.append((sy,sx))
    random.shuffle(start_list)

    for (sy,sx) in start_list:
        if backtrack(sy,sx) and len(path)==total:
            path2=local_improve_path(path[:],size,iterations=15)
            if is_chain_path(path2,size):
                print("[ForcefulBFS] Успех!")
                return path2
    print("[ForcefulBFS] Неуспех, возможно поле >20 или очень не повезло.")
    return None

# -------------------------------------------------------
# 7) ForcefulRandom
# -------------------------------------------------------
def generate_path_forceful_random(size):
    """
    Случайный проход с локальным backtrack, 
    пока не посетим все клетки или не исчерпаем 50 попыток.
    """
    print(f"[ForcefulRandom] size={size}, попробуем упорно.")
    total=size*size
    visited=[[False]*size for _ in range(size)]
    path=[]
    sy,sx=random.randint(0,size-1), random.randint(0,size-1)
    path.append((sy,sx))
    visited[sy][sx]=True

    def neighbors(y,x):
        dirs=[(-1,0),(1,0),(0,-1),(0,1)]
        random.shuffle(dirs)
        for (dy,dx) in dirs:
            ny,nx=y+dy,x+dx
            if 0<=ny<size and 0<=nx<size and not visited[ny][nx]:
                yield (ny,nx)

    def local_backtrack(steps):
        for _ in range(steps):
            if len(path)<1: 
                return
            (py,px)=path.pop()
            visited[py][px]=False

    tries=0
    while len(path)<total and tries<50:
        (cy,cx)=path[-1]
        nbs=list(neighbors(cy,cx))
        if not nbs:
            # откат
            local_backtrack(2)
            tries+=1
        else:
            (ny,nx)=random.choice(nbs)
            visited[ny][nx]=True
            path.append((ny,nx))

    if len(path)==total and is_chain_path(path,size):
        path=local_improve_path(path,size,iterations=15)
        if is_chain_path(path,size):
            print("[ForcefulRandom] Успех!")
            return path
    print("[ForcefulRandom] Неудача или поле слишком большое.")
    return None

# -------------------------------------------------------
# Итоговый генератор "hard" (7 алгоритмов) + проверка "не snake"
# -------------------------------------------------------
def generate_hard_path(size):
    """
    Порядок:
      1) Maze-based
      2) Hilbert (если 2^k)
      3) Sierpinski (если 2^k)
      4) Warnsdorff+ (8 попыток)
      5) BacktrackingDFS (max_attempts=10, no fallback snake)
      6) ForcefulBFS (для size <=20)
      7) ForcefulRandom
      Если всё -> fallback "column snake" + попытки 2-opt.
    """

    def try_algo(algo_func):
        path=algo_func()
        if path and len(path)==size*size:
            for _ in range(10):
                if not is_basic_snake(path,size):
                    return path
                path=local_improve_path(path,size,iterations=20)
                if not is_chain_path(path,size):
                    return None
        return None

    # 1) Maze-based
    r=try_algo(lambda: generate_path_maze_based(size))
    if r: return r
    # 2) Hilbert
    r=try_algo(lambda: generate_path_hilbert(size))
    if r: return r
    # 3) Sierpinski
    r=try_algo(lambda: generate_path_sierpinski(size))
    if r: return r
    # 4) Warnsdorff
    r=try_algo(lambda: generate_path_warnsdorff_improved(size,8,3))
    if r: return r
    # 5) Backtracking DFS
    r=try_algo(lambda: generate_path_backtracking_dfs(size,10))
    if r: return r
    # 6) ForcefulBFS (small fields)
    r=try_algo(lambda: generate_path_forceful_bfs(size))
    if r: return r
    # 7) ForcefulRandom
    r=try_algo(lambda: generate_path_forceful_random(size))
    if r: return r

    # финальный fallback: column_snake + 2opt
    print("[Hard] Всё провалилось, fallback -> column_snake + local improvements.")
    fallback=generate_column_snake_path(size)
    for _ in range(20):
        if not is_basic_snake(fallback,size):
            return fallback
        fallback=local_improve_path(fallback,size,iterations=20)
        if not is_chain_path(fallback,size):
            # если испортили цепочку - сделаем easy snake (хоть что-то),
            # но это крайне редкое событие
            return generate_easy_snake_path(size)
    return fallback

# -------------------------------------------------------
# Формирование Puzzle
# -------------------------------------------------------
def build_puzzle_from_path(path, size):
    pos={coord:i for i,coord in enumerate(path)}
    blocks=[[None]*size for _ in range(size)]
    def dir_from_to(a,b):
        (y1,x1)=a;(y2,x2)=b
        if y1==y2:
            return 'R' if x2>x1 else 'L'
        else:
            return 'D' if y2>y1 else 'U'
    n=len(path)
    for coord in path:
        i=pos[coord]
        (y,x)=coord
        if i==0:
            d=dir_from_to(coord,path[1])
            blocks[y][x]=Block('V' if d in ('U','D') else 'H',0)
        elif i==n-1:
            d=dir_from_to(path[n-2],coord)
            blocks[y][x]=Block('V' if d in ('U','D') else 'H',0)
        else:
            d1=dir_from_to(path[i-1],coord)
            d2=dir_from_to(coord,path[i+1])
            if d1 in ('U','D') and d2 in ('U','D'):
                blocks[y][x]=Block('V',0)
            elif d1 in ('L','R') and d2 in ('L','R'):
                blocks[y][x]=Block('H',0)
            else:
                pair=(d1,d2)
                if pair in [('U','L'),('L','U')]:
                    ori=0
                elif pair in [('U','R'),('R','U')]:
                    ori=1
                elif pair in [('R','D'),('D','R')]:
                    ori=2
                elif pair in [('D','L'),('L','D')]:
                    ori=3
                else:
                    ori=0
                blocks[y][x]=Block('C',ori)
    return Puzzle(size, blocks)

def scramble_puzzle_65(puzzle: Puzzle):
    all_blocks=[]
    for row in puzzle.blocks:
        all_blocks.extend(row)
    random.shuffle(all_blocks)
    n=len(all_blocks)
    k=int(n*0.65)
    for i, block in enumerate(all_blocks):
        if i<k:
            block.orientation=(block.orientation+1)%4

# -------------------------------------------------------
# Генерация 1 пазла
# -------------------------------------------------------
def generate_single_puzzle_data(difficulty, size):
    if difficulty=='easy':
        path=generate_easy_snake_path(size)
    elif difficulty=='medium':
        path=generate_snail_path(size)
    else:
        path=generate_hard_path(size)
    puzzle=build_puzzle_from_path(path,size)
    scramble_puzzle_65(puzzle)
    return puzzle.to_json_data()

# -------------------------------------------------------
# Предварительная генерация (puzzles.json)
# -------------------------------------------------------
PRECOMPUTED_FILE="puzzles.json"

def precompute_all_puzzles():
    if os.path.exists(PRECOMPUTED_FILE):
        with open(PRECOMPUTED_FILE,"r",encoding="utf-8") as f:
            puzzles_data=json.load(f)
        print("Загружены предвычисленные пазлы из", PRECOMPUTED_FILE)
        return puzzles_data
    else:
        difficulties=["easy","medium","hard"]
        sizes=range(10,101)
        count_each=10
        total_count=len(difficulties)*len(sizes)*count_each
        current=0
        puzzles_data={"easy":{}, "medium":{}, "hard":{}}
        print("Начинаем генерацию пазлов...")
        for diff in difficulties:
            for sz in sizes:
                puzzle_list=[]
                for _ in range(count_each):
                    print(f"\n=== Генерация пазла (diff={diff}, size={sz}), общий прогресс {current}/{total_count} ===")
                    p_data=generate_single_puzzle_data(diff,sz)
                    puzzle_list.append(p_data)
                    current+=1
                    print(f"=== Завершено: {current}/{total_count} пазлов ===\n")
                puzzles_data[diff][str(sz)] = puzzle_list
        with open(PRECOMPUTED_FILE,"w",encoding="utf-8") as f:
            json.dump(puzzles_data,f)
        print("Предвычисленные пазлы сохранены в", PRECOMPUTED_FILE)
        return puzzles_data

# -------------------------------------------------------
# Глобальный пул
# -------------------------------------------------------
puzzles_data={}

def get_precomputed_puzzle(difficulty, size):
    size_str=str(size)
    if difficulty not in puzzles_data:
        puzzles_data[difficulty]={}
    if size_str not in puzzles_data[difficulty]:
        puzzles_data[difficulty][size_str]=[]
    arr=puzzles_data[difficulty][size_str]
    if len(arr)>0:
        return arr.pop(0)
    else:
        return generate_single_puzzle_data(difficulty,size)

# -------------------------------------------------------
# Flask-маршруты
# -------------------------------------------------------
app = Flask(__name__)
app.secret_key = "some_secret_for_sessions"

@app.route("/")
def index():
    if 'user_id' in session:
        return redirect(url_for('choose_mode'))
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    login=request.form.get('login','').strip()
    password=request.form.get('password','').strip()
    nickname=request.form.get('nickname','').strip()
    if not login or not password or not nickname:
        return "Ошибка: все поля обязательны (логин, пароль, ник)."
    existing=User.query.filter_by(login=login).first()
    if existing:
        if existing.password!=password:
            return "Ошибка: неверный пароль!"
        session['user_id']=existing.id
        return redirect(url_for('choose_mode'))
    else:
        existing_nick=User.query.filter_by(nickname=nickname).first()
        if existing_nick:
            return "Ошибка: данный ник уже используется!"
        new_user=User(login=login,password=password,nickname=nickname)
        db.session.add(new_user)
        db.session.commit()
        session['user_id']=new_user.id
        return redirect(url_for('choose_mode'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route("/choose_mode")
def choose_mode():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user=User.query.get(session['user_id'])
    return render_template("mode.html", login=user.login, nickname=user.nickname)

@app.route("/start_game", methods=["POST"])
def start_game():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    mode=request.form.get('mode')
    difficulty=request.form.get('difficulty')
    size=int(request.form.get('size',10))
    if size<5:
        size=5
    if size>100:
        size=100

    session['mode']=mode
    session['difficulty']=difficulty
    session['size']=size

    if mode=="competition":
        session['start_time']=time.time()
        session['time_limit']=180
        session['score']=0
    else:
        session['start_time']=time.time()
        session['time_limit']=0
        session['score']=0

    p_data=get_precomputed_puzzle(difficulty,size)
    session['puzzle_data']=p_data
    return redirect(url_for('game'))

@app.route("/game")
def game():
    if 'user_id' not in session or 'mode' not in session:
        return redirect(url_for('index'))
    puzzle_data=session.get('puzzle_data')
    mode=session.get('mode')
    difficulty=session.get('difficulty')
    time_limit=session.get('time_limit',0)
    return render_template("game.html",
                           puzzle_data=puzzle_data,
                           mode=mode,
                           difficulty=difficulty,
                           time_limit=time_limit)

@app.route("/level_solved", methods=["POST"])
def level_solved():
    if 'user_id' not in session:
        return jsonify({"next_url": url_for('index')})
    data=request.get_json()
    elapsed=data.get('time',0)
    mode=session.get('mode')
    difficulty=session.get('difficulty')
    score=session.get('score')
    size=session.get('size')

    diff_mult={'easy':1,'medium':2,'hard':3}.get(difficulty,1)
    base_points=size
    time_penalty=max(1,elapsed)
    earned=int(diff_mult*base_points*(100/(10+time_penalty)))
    if earned<0:
        earned=0
    new_score=score+earned
    session['score']=new_score

    user=User.query.get(session['user_id'])
    pr_beaten=False
    if new_score>user.best_score:
        user.best_score=new_score
        db.session.commit()
        pr_beaten=True
    was_top=update_leaderboard_if_needed(user,new_score)

    if mode=="training":
        next_url=url_for('show_training_result',
                         points=earned,
                         time=elapsed,
                         pr=int(pr_beaten),
                         gt=int(was_top))
        return jsonify({"next_url":next_url})
    else:
        start_time=session.get('start_time')
        if not start_time:
            return jsonify({"next_url":url_for('time_is_up')})
        now=time.time()
        if now-start_time>=180:
            return jsonify({"next_url":url_for('time_is_up')})
        else:
            p_data=get_precomputed_puzzle(difficulty,size)
            session['puzzle_data']=p_data
            return jsonify({"next_url":url_for('game')})

@app.route("/show_training_result")
def show_training_result():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    points=request.args.get('points','0')
    time_sec=request.args.get('time','0')
    pr=request.args.get('pr','0')
    gt=request.args.get('gt','0')
    personal_record=(pr=='1')
    global_top=(gt=='1')
    return render_template("training_result.html",
                           points=points,
                           time_sec=time_sec,
                           personal_record=personal_record,
                           global_top=global_top)

@app.route("/time_is_up")
def time_is_up():
    if 'user_id' not in session or session.get('mode')!='competition':
        return redirect(url_for('index'))
    score=session.get('score',0)
    user=User.query.get(session['user_id'])
    event=ScoreEvent(user_id=user.id, score=score, timestamp=time.time())
    db.session.add(event)
    if score>user.best_score:
        user.best_score=score
    db.session.commit()
    was_top=update_leaderboard_if_needed(user,score)
    session.pop('mode',None)
    session.pop('puzzle_data',None)
    session.pop('time_limit',None)
    session.pop('start_time',None)

    all_users=User.query.all()
    sorted_users=sorted(all_users, key=lambda u: u.best_score, reverse=True)
    pos=1
    for u in sorted_users:
        if u.id==user.id:
            break
        pos+=1

    return render_template("time_is_up.html", score=score, position=pos)

@app.route("/profile", methods=["GET","POST"])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user=User.query.get(session['user_id'])
    if request.method=="POST":
        new_nick=request.form.get('nickname','').strip()
        if new_nick and new_nick!=user.nickname:
            existing=User.query.filter_by(nickname=new_nick).first()
            if existing and existing.id!=user.id:
                return "Ошибка: такой ник уже существует!"
            user.nickname=new_nick
        file=request.files.get('avatar')
        if file and file.filename:
            filename=secure_filename(file.filename)
            upload_path=os.path.join('static','avatars',filename)
            os.makedirs(os.path.dirname(upload_path), exist_ok=True)
            file.save(upload_path)
            user.avatar='/'+upload_path
        db.session.commit()
        return redirect(url_for('profile'))
    return render_template("profile.html", user=user)

@app.route("/poll_announcements", methods=["GET"])
def poll_announcements():
    global announcement
    if announcement:
        return jsonify({"has_announcement":True,"announcement":announcement})
    return jsonify({"has_announcement":False})

# -------------------------------------------------------
# MAIN
# -------------------------------------------------------
if __name__=="__main__":
    puzzles_data=precompute_all_puzzles()
    app.run(host="0.0.0.0", port=221, debug=True)











