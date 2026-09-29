import pygame
import sys
import math
import random

# ==========================================
# 1. 환경 설정 및 상수
# ==========================================
WIDTH, HEIGHT = 960, 540
FPS = 60
TILE_SIZE = 40

# 색상 팔레트
COLORS = {
    'bg_main': (30, 30, 30),
    'W': (45, 45, 45),       # 벽
    '1': (180, 80, 80),      # 빨간 방
    '2': (80, 180, 80),      # 초록 방
    '3': (80, 80, 180),      # 파란 방
    '4': (180, 180, 80),     # 노란 방
    'cham_default': (255, 0, 255), # 카멜레온 기본색 (눈에 띄는 마젠타)
    'white': (255, 255, 255),
    'black': (0, 0, 0),
    'red': (255, 0, 0)
}

# 맵 데이터 (ASCII 하드코딩)
# W: 충돌 벽, 1~4: 방의 배경색(숨을 수 있는 색), .: 빈 공간(이동 통로)
LEVEL_MAP = [
    "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW",
    "W111111111111W222222222222W333333333333W4444444W",
    "W111111111111W222222222222W333333333333W4444444W",
    "W111111111111W222222222222W333333333333W4444444W",
    "W111111111111.222222222222.333333333333.4444444W",
    "W111111111111W222222222222W333333333333W4444444W",
    "WWWWWW.WWWWWWWWWWWWW.WWWWWWWWWWWWW.WWWWWWWWWWWWW",
    "W333333333333W444444444444W111111111111W2222222W",
    "W333333333333W444444444444W111111111111W2222222W",
    "W333333333333W444444444444W111111111111W2222222W",
    "W333333333333.444444444444.111111111111.2222222W",
    "W333333333333W444444444444W111111111111W2222222W",
    "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW",
]

WORLD_WIDTH = len(LEVEL_MAP[0]) * TILE_SIZE
WORLD_HEIGHT = len(LEVEL_MAP) * TILE_SIZE

# ==========================================
# 2. 객체 클래스
# ==========================================
class Chameleon:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 30, 30)
        self.vx = 0
        self.vy = 0
        self.speed = 5
        self.jump_power = -12
        self.gravity = 0.6
        self.color = COLORS['cham_default']
        self.is_frozen = False
        self.on_ground = False
        
        self.blink_timer = random.randint(600, 900) # 10~15초 (60fps 기준)
        self.is_blinking = False

    def update(self, walls):
        if not self.is_frozen:
            # 입력 처리
            keys = pygame.key.get_pressed()
            self.vx = 0
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                self.vx = -self.speed
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                self.vx = self.speed
                
            if (keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_SPACE]) and self.on_ground:
                self.vy = self.jump_power
                self.on_ground = False

            # 중력 및 Y축 물리
            self.vy += self.gravity
            
            # X축 충돌 처리
            self.rect.x += self.vx
            for w in walls:
                if self.rect.colliderect(w):
                    if self.vx > 0: self.rect.right = w.left
                    elif self.vx < 0: self.rect.left = w.right
                    
            # Y축 충돌 처리
            self.rect.y += self.vy
            self.on_ground = False
            for w in walls:
                if self.rect.colliderect(w):
                    if self.vy > 0: 
                        self.rect.bottom = w.top
                        self.on_ground = True
                        self.vy = 0
                    elif self.vy < 0:
                        self.rect.top = w.bottom
                        self.vy = 0

        # 눈 깜빡임 로직
        self.blink_timer -= 1
        if self.blink_timer <= 0:
            self.is_blinking = True
            self.blink_timer = random.randint(900, 1200) # 다시 15~20초 뒤
        if self.is_blinking and self.blink_timer < (900 - 6): # 0.1초(6프레임) 유지
            self.is_blinking = False

    def draw(self, surface):
        pygame.draw.rect(surface, self.color, self.rect)
        # 얼어있지 않거나 깜빡일 때 눈 그리기
        if not self.is_frozen or self.is_blinking:
            eye_x = self.rect.x + 20 if self.vx >= 0 else self.rect.x + 5
            eye_y = self.rect.y + 8
            pygame.draw.rect(surface, COLORS['white'], (eye_x, eye_y, 6, 6))
            pygame.draw.rect(surface, COLORS['black'], (eye_x+2, eye_y+2, 2, 2))

class Camera:
    def __init__(self):
        self.x = 0
        self.y = 0

    def apply(self, rect):
        return pygame.Rect(rect.x - self.x, rect.y - self.y, rect.width, rect.height)

    def update(self, target_x, target_y):
        # 타겟을 화면 중앙에 오도록 보간 (스무딩)
        desired_x = target_x - WIDTH // 2
        desired_y = target_y - HEIGHT // 2
        self.x += (desired_x - self.x) * 0.1
        self.y += (desired_y - self.y) * 0.1
        
        # 맵 경계 제한
        self.x = max(0, min(self.x, WORLD_WIDTH - WIDTH))
        self.y = max(0, min(self.y, WORLD_HEIGHT - HEIGHT))

# ==========================================
# 3. 메인 게임 루프 및 상태 머신
# ==========================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("MECCHA CHAMELEON 2D (Single File Edition)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("malgungothic", 24, bold=True)
    big_font = pygame.font.SysFont("malgungothic", 64, bold=True)

    # 맵 파싱 및 렌더링
    walls = []
    bg_surface = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))
    bg_surface.fill(COLORS['bg_main'])
    
    for row, line in enumerate(LEVEL_MAP):
        for col, char in enumerate(line):
            x, y = col * TILE_SIZE, row * TILE_SIZE
            if char == 'W':
                walls.append(pygame.Rect(x, y, TILE_SIZE, TILE_SIZE))
                pygame.draw.rect(bg_surface, COLORS['W'], (x, y, TILE_SIZE, TILE_SIZE))
            elif char in COLORS:
                pygame.draw.rect(bg_surface, COLORS[char], (x, y, TILE_SIZE, TILE_SIZE))

    # 객체 초기화
    chameleon = Chameleon(60, 60)
    camera = Camera()
    
    # 상태 관리
    state = "CHAMELEON" # CHAMELEON, TRANSITION, HUNTER, RESULT
    timer = 60 * FPS # 60초
    
    # 헌터 전용 변수
    hunter_cam_x, hunter_cam_y = chameleon.rect.centerx, chameleon.rect.centery
    hunter_cooldown = 0
    click_effect = [] # (x, y, timer)
    winner = ""

    # 전환 효과 변수
    transition_alpha = 0
    countdown = 3 * FPS

    running = True
    while running:
        dt = clock.tick(FPS)
        mouse_x, mouse_y = pygame.mouse.get_pos()
        world_mouse_x = mouse_x + camera.x
        world_mouse_y = mouse_y + camera.y

        # 이벤트 처리
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            if state == "CHAMELEON":
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_TAB:
                        chameleon.is_frozen = not chameleon.is_frozen
                    if event.key == pygame.K_RETURN and chameleon.is_frozen:
                        # 위장 완료, 턴 종료
                        state = "TRANSITION"
                        transition_alpha = 0
                
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if chameleon.is_frozen:
                        # 스포이드: 맵 표면의 색상 추출
                        if 0 <= world_mouse_x < WORLD_WIDTH and 0 <= world_mouse_y < WORLD_HEIGHT:
                            picked_color = bg_surface.get_at((int(world_mouse_x), int(world_mouse_y)))
                            chameleon.color = picked_color

            elif state == "TRANSITION":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and transition_alpha >= 255:
                    if countdown == 3 * FPS: # 카운트다운 시작
                        countdown -= 1

            elif state == "HUNTER":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and hunter_cooldown <= 0:
                    # 지목 (Accuse)
                    dist = math.hypot(world_mouse_x - chameleon.rect.centerx, world_mouse_y - chameleon.rect.centery)
                    if dist <= 24: # 적중
                        winner = "HUNTER WINS!"
                        state = "RESULT"
                        timer = 5 * FPS
                    else: # 빗나감
                        hunter_cooldown = 3 * FPS
                        click_effect.append([world_mouse_x, world_mouse_y, 30]) # X 표시 이펙트

            elif state == "RESULT":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    # 재시작 (원래는 함수로 분리하는 것이 좋음)
                    main()
                    return

        # ==========================================
        # 상태별 업데이트
        # ==========================================
        if state == "CHAMELEON":
            chameleon.update(walls)
            camera.update(chameleon.rect.centerx, chameleon.rect.centery)
            timer -= 1
            if timer <= 0:
                state = "TRANSITION"

        elif state == "TRANSITION":
            if transition_alpha < 255:
                transition_alpha += 5
            elif countdown < 3 * FPS:
                countdown -= 1
                if countdown <= 0:
                    state = "HUNTER"
                    timer = 120 * FPS
                    hunter_cam_x, hunter_cam_y = WORLD_WIDTH // 2, WORLD_HEIGHT // 2 # 헌터 시점 초기화

        elif state == "HUNTER":
            # 헌터 카메라 자유 이동
            keys = pygame.key.get_pressed()
            cam_speed = 15
            if keys[pygame.K_LEFT] or keys[pygame.K_a]: hunter_cam_x -= cam_speed
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]: hunter_cam_x += cam_speed
            if keys[pygame.K_UP] or keys[pygame.K_w]: hunter_cam_y -= cam_speed
            if keys[pygame.K_DOWN] or keys[pygame.K_s]: hunter_cam_y += cam_speed
            
            # 마우스 엣지 패닝(화면 끝에 마우스를 대면 카메라 이동)
            if mouse_x < 50: hunter_cam_x -= cam_speed
            if mouse_x > WIDTH - 50: hunter_cam_x += cam_speed
            if mouse_y < 50: hunter_cam_y -= cam_speed
            if mouse_y > HEIGHT - 50: hunter_cam_y += cam_speed

            camera.update(hunter_cam_x, hunter_cam_y)
            
            if hunter_cooldown > 0:
                hunter_cooldown -= 1
                
            timer -= 1
            if timer <= 0:
                winner = "CHAMELEON WINS!"
                state = "RESULT"
                timer = 5 * FPS
            
            chameleon.blink_timer -= 1
            if chameleon.blink_timer <= 0:
                chameleon.is_blinking = True
                chameleon.blink_timer = random.randint(900, 1200)
            if chameleon.is_blinking and chameleon.blink_timer < (900 - 6):
                chameleon.is_blinking = False

        elif state == "RESULT":
            camera.update(chameleon.rect.centerx, chameleon.rect.centery)

        # ==========================================
        # 렌더링
        # ==========================================
        screen.fill(COLORS['bg_main'])
        
        # 1. 배경 출력
        screen.blit(bg_surface, (-camera.x, -camera.y))
        
        # 2. 카멜레온 출력
        cam_cham_rect = camera.apply(chameleon.rect)
        if state != "HUNTER" or chameleon.is_blinking or state == "RESULT":
            # 헌터 턴일 때는 보이지 않음. 단, 눈 깜빡일 때와 결과 창에서는 보임
            pygame.draw.rect(screen, chameleon.color, cam_cham_rect)
            if not chameleon.is_frozen or chameleon.is_blinking or state == "RESULT":
                eye_x = cam_cham_rect.x + (20 if chameleon.vx >= 0 else 5)
                eye_y = cam_cham_rect.y + 8
                pygame.draw.rect(screen, COLORS['white'], (eye_x, eye_y, 6, 6))
                pygame.draw.rect(screen, COLORS['black'], (eye_x+2, eye_y+2, 2, 2))

        # 3. UI 및 이펙트 출력
        if state == "CHAMELEON":
            ui_text = font.render(f"숨을 시간: {max(0, timer//FPS)}초 | TAB: 고정/해제 | 고정 후 마우스클릭: 색상 추출 | ENTER: 턴 종료", True, COLORS['white'])
            screen.blit(ui_text, (10, 10))
            if chameleon.is_frozen:
                freeze_txt = font.render("[ 위장 모드 활성화 - 마우스로 배경색을 클릭하세요 ]", True, COLORS['white'])
                screen.blit(freeze_txt, (WIDTH//2 - freeze_txt.get_width()//2, HEIGHT - 50))
                
        elif state == "TRANSITION":
            overlay = pygame.Surface((WIDTH, HEIGHT))
            overlay.fill((0, 0, 0))
            overlay.set_alpha(transition_alpha)
            screen.blit(overlay, (0, 0))
            
            if transition_alpha >= 255:
                if countdown == 3 * FPS:
                    msg = big_font.render("카멜레온은 눈을 감아주세요.", True, COLORS['white'])
                    msg2 = font.render("헌터가 자리에 앉아 마우스를 클릭하면 시작됩니다.", True, (150, 150, 150))
                    screen.blit(msg, (WIDTH//2 - msg.get_width()//2, HEIGHT//2 - 50))
                    screen.blit(msg2, (WIDTH//2 - msg2.get_width()//2, HEIGHT//2 + 50))
                else:
                    count_msg = big_font.render(str(math.ceil(countdown/FPS)), True, COLORS['red'])
                    screen.blit(count_msg, (WIDTH//2 - count_msg.get_width()//2, HEIGHT//2 - count_msg.get_height()//2))

        elif state == "HUNTER":
            ui_text = font.render(f"찾을 시간: {max(0, timer//FPS)}초 | WASD/마우스가장자리: 카메라 이동 | 마우스 좌클릭: 지목", True, COLORS['white'])
            screen.blit(ui_text, (10, 10))
            
            # 빗나감 쿨다운 UI
            if hunter_cooldown > 0:
                cd_text = big_font.render(f"쿨다운: {math.ceil(hunter_cooldown/FPS)}", True, COLORS['red'])
                screen.blit(cd_text, (WIDTH//2 - cd_text.get_width()//2, HEIGHT - 100))
                
            # X 이펙트
            for effect in click_effect[:]:
                ex, ey, et = effect
                screen_ex, screen_ey = ex - camera.x, ey - camera.y
                pygame.draw.line(screen, COLORS['red'], (screen_ex-10, screen_ey-10), (screen_ex+10, screen_ey+10), 4)
                pygame.draw.line(screen, COLORS['red'], (screen_ex-10, screen_ey+10), (screen_ex+10, screen_ey-10), 4)
                effect[2] -= 1
                if effect[2] <= 0:
                    click_effect.remove(effect)

        elif state == "RESULT":
            win_msg = big_font.render(winner, True, COLORS['red'] if "HUNTER" in winner else COLORS['2'])
            info_msg = font.render("ENTER를 누르면 다시 시작합니다.", True, COLORS['white'])
            screen.blit(win_msg, (WIDTH//2 - win_msg.get_width()//2, HEIGHT//2 - 50))
            screen.blit(info_msg, (WIDTH//2 - info_msg.get_width()//2, HEIGHT//2 + 30))
            # 카멜레온 위치 강조
            pygame.draw.rect(screen, COLORS['red'], cam_cham_rect, 4)

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()