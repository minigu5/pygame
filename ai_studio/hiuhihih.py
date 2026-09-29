import pygame
import sys
import math
import os

# ==========================================
# 1. 게임 기본 설정 및 상수
# ==========================================
WIDTH, HEIGHT = 960, 540
FPS = 60

# 물리 엔진 설정
GRAVITY = 2000      # 중력
JUMP_VEL = -620     # 점프력
MOVE_SPEED = 250    # 이동 속도
PLAYER_SIZE = (24, 32)

# 타이머 설정 (엄격한 타이머 적용)
HIDE_TIME_LIMIT = 60.0   # 숨는 시간 60초
SEEK_TIME_LIMIT = 120.0  # 찾는 시간 120초
PENALTY_TIME = 3.0       # 빗나갈 시 쿨타임 3초

# ==========================================
# 2. 게임 메인 클래스 (플레이어)
# ==========================================
class Chameleon:
    def __init__(self, start_x, start_y):
        self.rect = pygame.Rect(start_x, start_y, PLAYER_SIZE[0], PLAYER_SIZE[1])
        self.vx = 0
        self.vy = 0
        self.on_ground = False
        self.frozen = False
        self.color = (255, 0, 0)  # 초기 색상 (빨간색)

    def update(self, dt, solid_rects):
        if self.frozen:
            self.vx = 0
            self.vy = 0
            return

        # 중력 적용
        self.vy += GRAVITY * dt
        
        # X축 이동 및 충돌
        self.rect.x += self.vx * dt
        for rect in solid_rects:
            if self.rect.colliderect(rect):
                if self.vx > 0:
                    self.rect.right = rect.left
                elif self.vx < 0:
                    self.rect.left = rect.right
                self.vx = 0

        # Y축 이동 및 충돌
        self.rect.y += self.vy * dt
        self.on_ground = False
        for rect in solid_rects:
            if self.rect.colliderect(rect):
                if self.vy > 0:
                    self.rect.bottom = rect.top
                    self.on_ground = True
                elif self.vy < 0:
                    self.rect.top = rect.bottom
                self.vy = 0

    def draw(self, surface, camera_x, camera_y):
        # 카메라 오프셋을 적용해 그리기
        draw_rect = self.rect.copy()
        draw_rect.x -= camera_x
        draw_rect.y -= camera_y
        pygame.draw.rect(surface, self.color, draw_rect)

# ==========================================
# 3. 메인 게임 루프 함수
# ==========================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("메챠 카멜레온 2D: 단일 파일 에디션")
    clock = pygame.time.Clock()

    # 한글 폰트 설정 (없으면 기본 폰트)
    font_name = pygame.font.match_font('malgungothic, applegothic, dotum, arial')
    font = pygame.font.Font(font_name, 32)
    big_font = pygame.font.Font(font_name, 64)

    # 배경 맵 이미지 로드 (map.png)
    if os.path.exists("map.png"):
        bg_img = pygame.image.load("map.png").convert()
    else:
        # 이미지가 없을 경우를 대비한 더미(가짜) 배경
        bg_img = pygame.Surface((WIDTH * 2, HEIGHT * 2))
        bg_img.fill((50, 50, 60))
        pygame.draw.rect(bg_img, (100, 100, 150), (200, 200, 300, 300))
        print("경고: map.png 파일을 찾을 수 없어 임시 배경을 사용합니다.")

    map_w, map_h = bg_img.get_size()

    # 지형(바닥) 설정 - 이미지의 맨 아래쪽을 밟을 수 있는 바닥으로 만듬
    solid_rects = [
        pygame.Rect(0, map_h - 40, map_w, 40), # 맨 밑 바닥
        pygame.Rect(0, -100, 10, map_h + 100), # 좌측 벽
        pygame.Rect(map_w - 10, -100, 10, map_h + 100) # 우측 벽
    ]

    player = Chameleon(map_w // 2, map_h - 100)
    
    # 게임 상태: "HIDE", "TRANSITION", "SEEK", "RESULT"
    state = "HIDE"
    
    timer = HIDE_TIME_LIMIT
    penalty_timer = 0.0
    winner = None

    camera_x, camera_y = 0, 0

    while True:
        dt = clock.tick(FPS) / 1000.0
        
        # -----------------------------------
        # 이벤트 처리
        # -----------------------------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if state == "HIDE":
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE and player.on_ground and not player.frozen:
                        player.vy = JUMP_VEL
                    if event.key == pygame.K_TAB:
                        player.frozen = not player.frozen  # 고정 모드 토글 (공중부양 가능)
                
                # 스포이드 (색상 추출)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if player.frozen:
                        mx, my = pygame.mouse.get_pos()
                        world_x = mx + camera_x
                        world_y = my + camera_y
                        if 0 <= world_x < map_w and 0 <= world_y < map_h:
                            player.color = bg_img.get_at((int(world_x), int(world_y)))[:3]

            elif state == "TRANSITION":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    state = "SEEK"
                    timer = SEEK_TIME_LIMIT

            elif state == "SEEK":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if penalty_timer <= 0:
                        mx, my = pygame.mouse.get_pos()
                        world_x = mx + camera_x
                        world_y = my + camera_y
                        
                        # 지목 판정 (클릭한 위치가 플레이어 중심점 기준 30px 이내인지)
                        px = player.rect.centerx
                        py = player.rect.centery
                        dist = math.hypot(world_x - px, world_y - py)
                        
                        if dist <= 30:
                            state = "RESULT"
                            winner = "헌터 (찾는 자)"
                        else:
                            penalty_timer = PENALTY_TIME # 빗나감 (쿨타임)

            elif state == "RESULT":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    # 게임 초기화 및 재시작
                    player = Chameleon(map_w // 2, map_h - 100)
                    state = "HIDE"
                    timer = HIDE_TIME_LIMIT

        # -----------------------------------
        # 로직 업데이트
        # -----------------------------------
        keys = pygame.key.get_pressed()

        if state == "HIDE":
            timer -= dt
            if timer <= 0:
                player.frozen = True  # 시간 초과 시 그 자리에 강제 고정
                state = "TRANSITION"

            if not player.frozen:
                player.vx = 0
                if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                    player.vx = -MOVE_SPEED
                if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                    player.vx = MOVE_SPEED

            player.update(dt, solid_rects)

            # 카멜레온 시점 카메라 추적
            target_cx = player.rect.centerx - WIDTH // 2
            target_cy = player.rect.centery - HEIGHT // 2
            camera_x += (target_cx - camera_x) * 10 * dt
            camera_y += (target_cy - camera_y) * 10 * dt

        elif state == "SEEK":
            timer -= dt
            if timer <= 0:
                state = "RESULT"
                winner = "카멜레온 (숨는 자)"
            
            if penalty_timer > 0:
                penalty_timer -= dt

            # 헌터 시점 자유 카메라 이동 (WASD 또는 방향키)
            cam_speed = 400 * dt
            if keys[pygame.K_LEFT] or keys[pygame.K_a]: camera_x -= cam_speed
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]: camera_x += cam_speed
            if keys[pygame.K_UP] or keys[pygame.K_w]: camera_y -= cam_speed
            if keys[pygame.K_DOWN] or keys[pygame.K_s]: camera_y += cam_speed

        # 카메라 화면 밖으로 안 나가게 제한
        camera_x = max(0, min(camera_x, map_w - WIDTH))
        camera_y = max(0, min(camera_y, map_h - HEIGHT))

        # -----------------------------------
        # 렌더링 (화면 그리기)
        # -----------------------------------
        if state == "TRANSITION":
            screen.fill((0, 0, 0)) # 암전
            txt1 = font.render("숨기 종료! 헌터는 자리에 앉아주세요.", True, (255, 255, 255))
            txt2 = font.render("[ Enter ] 를 누르면 찾기(120초) 시작", True, (200, 200, 200))
            screen.blit(txt1, (WIDTH//2 - txt1.get_width()//2, HEIGHT//2 - 50))
            screen.blit(txt2, (WIDTH//2 - txt2.get_width()//2, HEIGHT//2 + 10))

        else:
            # 맵 그리기
            screen.blit(bg_img, (-camera_x, -camera_y))

            # 플레이어 그리기 (헌터 턴일 때는 완벽하게 그려짐 = 숨겨짐 효과)
            player.draw(screen, camera_x, camera_y)

            # UI 렌더링
            if state == "HIDE":
                ui_txt = font.render(f"숨기 남은시간: {int(timer)}초 | TAB: 위장모드 켜기/끄기", True, (255, 255, 255))
                screen.blit(ui_txt, (20, 20))
                
                if player.frozen:
                    freeze_txt = font.render("위장모드 (마우스 좌클릭으로 배경색 추출)", True, (0, 255, 0))
                    screen.blit(freeze_txt, (20, 60))

            elif state == "SEEK":
                ui_txt = font.render(f"찾기 남은시간: {int(timer)}초 | WASD: 카메라 이동 | 클릭: 지목", True, (255, 255, 255))
                screen.blit(ui_txt, (20, 20))

                if penalty_timer > 0:
                    pen_txt = big_font.render(f"쿨타임! X", True, (255, 0, 0))
                    screen.blit(pen_txt, (WIDTH//2 - pen_txt.get_width()//2, HEIGHT//2))
            
            elif state == "RESULT":
                overlay = pygame.Surface((WIDTH, HEIGHT))
                overlay.set_alpha(150)
                overlay.fill((0, 0, 0))
                screen.blit(overlay, (0, 0))

                # 카멜레온 위치 강조 (빨간 테두리)
                highlight_rect = player.rect.copy()
                highlight_rect.x -= camera_x
                highlight_rect.y -= camera_y
                pygame.draw.rect(screen, (255, 0, 0), highlight_rect, 5)

                res_txt = big_font.render(f"승리: {winner}", True, (255, 215, 0))
                guide_txt = font.render("[ Enter ] 를 눌러 다시하기", True, (255, 255, 255))
                
                screen.blit(res_txt, (WIDTH//2 - res_txt.get_width()//2, HEIGHT//2 - 60))
                screen.blit(guide_txt, (WIDTH//2 - guide_txt.get_width()//2, HEIGHT//2 + 40))

        pygame.display.flip()

if __name__ == "__main__":
    main()