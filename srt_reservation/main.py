# -*- coding: utf-8 -*-
import os
import time
from random import randint
from datetime import datetime
from selenium import webdriver
# [수정] webdriver_manager 관련 import 제거
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException, WebDriverException, UnexpectedAlertPresentException, NoAlertPresentException

from srt_reservation.exceptions import InvalidStationNameError, InvalidDateError, InvalidDateFormatError, InvalidTimeFormatError
from srt_reservation.validation import station_list
from selenium.webdriver.common.alert import Alert
from slack_sdk import WebClient

import smtplib
from email.mime.text import MIMEText

class SRT:
    def __init__(self, dpt_stn, arr_stn, dpt_dt, dpt_tm, order_trains_to_check=2, want_reserve=False, slack_token = "", gmail_send="", gmail_app_pw="", gmail_receive=""):
        """
        :param dpt_stn: SRT 출발역
        :param arr_stn: SRT 도착역
        :param dpt_dt: 출발 날짜 YYYYMMDD 형태 ex) 20220115
        :param dpt_tm: 출발 시간 hh 형태, 반드시 짝수 ex) 06, 08, 14, ...
        :param order_trains_to_check: 검색 결과 중 예약 가능 여부 확인할 기차의 수 ex) 2일 경우 상위 2개 확인
        :param want_reserve: 예약 대기가 가능할 경우 선택 여부
        """
        self.login_id = None
        self.login_psw = None

        self.dpt_stn = dpt_stn
        self.arr_stn = arr_stn
        self.dpt_dt = dpt_dt
        self.dpt_tm = dpt_tm

        self.order_trains_to_check = order_trains_to_check
        self.want_reserve = want_reserve
        self.driver = None

        self.is_booked = False  # 예약 완료 되었는지 확인용
        self.cnt_refresh = 0  # 새로고침 회수 기록
        self.client = WebClient(slack_token)

        self.gmail_send = gmail_send
        self.gmail_app_pw = gmail_app_pw
        self.gmail_receive = gmail_receive

        self.check_input()

    def check_input(self):
        if self.dpt_stn not in station_list:
            raise InvalidStationNameError(f"출발역 오류. '{self.dpt_stn}' 은/는 목록에 없습니다.")
        if self.arr_stn not in station_list:
            raise InvalidStationNameError(f"도착역 오류. '{self.arr_stn}' 은/는 목록에 없습니다.")
        if not str(self.dpt_dt).isnumeric():
            raise InvalidDateFormatError("날짜는 숫자로만 이루어져야 합니다.")
        try:
            datetime.strptime(str(self.dpt_dt), '%Y%m%d')
        except ValueError:
            raise InvalidDateError("날짜가 잘못 되었습니다. YYYYMMDD 형식으로 입력해주세요.")

    def set_log_info(self, login_id, login_psw):
        self.login_id = login_id
        self.login_psw = login_psw

    def run_driver(self):
        # [수정] Selenium Manager(내장 기능)를 사용하여 드라이버 자동 실행
        try:
            self.driver = webdriver.Chrome()
        except Exception as e:
            print(f"드라이버 실행 오류: {e}")
            print("Selenium을 최신 버전으로 업데이트 해주세요: pip install --upgrade selenium")

    def login(self):
        self.driver.get('https://etk.srail.co.kr/cmc/01/selectLoginForm.do')
        self.driver.implicitly_wait(15)
        self.driver.find_element(By.ID, 'srchDvNm01').send_keys(str(self.login_id))
        self.driver.find_element(By.ID, 'hmpgPwdCphd01').send_keys(str(self.login_psw))
        self.driver.find_element(By.XPATH, '//*[@id="login-form"]/fieldset/div[1]/div[2]/div[2]/div/div[2]/input').click()
        
        # [중요 수정] 로그인 처리 및 세션 생성을 위해 충분히 대기 (1초)
        print("로그인 처리 대기 중...")
        time.sleep(1) 
        
        # [추가] 비밀번호 변경 안내 팝업 등이 뜨면 닫아야 함 (창 핸들링)
        # 메인 창(윈도우) 개수가 1개보다 많으면 팝업이 뜬 것임
        if len(self.driver.window_handles) > 1:
            current_window = self.driver.current_window_handle
            # 모든 팝업 닫기
            for handle in self.driver.window_handles:
                if handle != current_window:
                    self.driver.switch_to.window(handle)
                    self.driver.close()
            # 다시 메인 창으로 복귀
            self.driver.switch_to.window(current_window)
            
        return self.driver

    def check_login(self):
        menu_text = self.driver.find_element(By.CSS_SELECTOR, "#wrap > div.header.header-e > div.global.clear > div").text
        if "환영합니다" in menu_text:
            return True
        else:
            return False

    def go_search(self):
        # 기차 조회 페이지로 이동
        self.driver.get('https://etk.srail.kr/hpg/hra/01/selectScheduleList.do')
        self.driver.implicitly_wait(5)

        # 출발지 입력
        elm_dpt_stn = self.driver.find_element(By.ID, 'dptRsStnCdNm')
        elm_dpt_stn.clear()
        elm_dpt_stn.send_keys(self.dpt_stn)

        # 도착지 입력
        elm_arr_stn = self.driver.find_element(By.ID, 'arvRsStnCdNm')
        elm_arr_stn.clear()
        elm_arr_stn.send_keys(self.arr_stn)

        # 출발 날짜 입력
        elm_dpt_dt = self.driver.find_element(By.ID, "dptDt")
        self.driver.execute_script("arguments[0].setAttribute('style','display: True;')", elm_dpt_dt)
        Select(self.driver.find_element(By.ID, "dptDt")).select_by_value(self.dpt_dt)

        # 출발 시간 입력
        elm_dpt_tm = self.driver.find_element(By.ID, "dptTm")
        self.driver.execute_script("arguments[0].setAttribute('style','display: True;')", elm_dpt_tm)
        Select(self.driver.find_element(By.ID, "dptTm")).select_by_visible_text(self.dpt_tm)

        print("기차를 조회합니다")
        print(f"출발역:{self.dpt_stn}, 도착역:{self.arr_stn}\n날짜:{self.dpt_dt}, 시간: {self.dpt_tm}시 이후\n{self.order_trains_to_check}번째 기차 중 예약")
        print(f"예약 대기 사용: {self.want_reserve}")

        self.driver.find_element(By.XPATH, "//input[@value='조회하기']").click()
        self.driver.implicitly_wait(5)
        time.sleep(1)

    def book_ticket(self, standard_seat, i):
        # standard_seat는 일반석 검색 결과 텍스트
        
        if "예약하기" in standard_seat:
            print("예약 가능 클릭")

            # Error handling in case that click does not work
            try:
                self.driver.find_element(By.CSS_SELECTOR,
                                         f"#result-form > fieldset > div.tbl_wrap.th_thead > table > tbody > tr:nth-child({i}) > td:nth-child(7) > a").click()
            except ElementClickInterceptedException as err:
                print(err)
                self.driver.find_element(By.CSS_SELECTOR,
                                         f"#result-form > fieldset > div.tbl_wrap.th_thead > table > tbody > tr:nth-child({i}) > td:nth-child(7) > a").send_keys(
                    Keys.ENTER)
            finally:
                self.driver.implicitly_wait(3)

            # 예약이 성공하면
            try:
                if self.driver.find_elements(By.ID, 'isFalseGotoMain'):
                    self.is_booked = True
                    print("예약 성공")
                    try:
                        self.send_email("SRT 예매에 성공했습니다! 빨리 결제하세요!")
                        self.client.chat_postMessage(channel="#alarm", text="book sucess")
                    except:
                        pass
                    return self.driver
                else:
                    print("잔여석 없음. 다시 검색")
                    self.driver.back()  # 뒤로가기
                    self.driver.implicitly_wait(5)
            except UnexpectedAlertPresentException:
                return True



    def refresh_result(self):
        submit = self.driver.find_element(By.XPATH, "//input[@value='조회하기']")
        self.driver.execute_script("arguments[0].click();", submit)
        self.cnt_refresh += 1
        print(f"새로고침 {self.cnt_refresh}회")
        self.driver.implicitly_wait(10)
        time.sleep(0.5)

    def reserve_ticket(self, reservation, i):
        if "신청하기" in reservation:
            print("예약 대기 완료")
            self.driver.find_element(By.CSS_SELECTOR,
                                     f"#result-form > fieldset > div.tbl_wrap.th_thead > table > tbody > tr:nth-child({i}) > td:nth-child(8) > a").click()
            self.is_booked = True
            return self.is_booked

    def check_result(self):
        while True:
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
            except NoAlertPresentException:
                pass
            except Exception:
                pass

            for i in self.order_trains_to_check:
                try:
                    standard_seat = self.driver.find_element(By.CSS_SELECTOR, f"#result-form > fieldset > div.tbl_wrap.th_thead > table > tbody > tr:nth-child({i}) > td:nth-child(7)").text
                    reservation = self.driver.find_element(By.CSS_SELECTOR, f"#result-form > fieldset > div.tbl_wrap.th_thead > table > tbody > tr:nth-child({i}) > td:nth-child(8)").text
                except StaleElementReferenceException:
                    standard_seat = "매진"
                    reservation = "매진"
                except Exception:
                    standard_seat = "확인불가"
                    reservation = "확인불가"

                if self.book_ticket(standard_seat, i):
                    return self.driver

                if self.want_reserve:
                    self.reserve_ticket(reservation, i)

            if self.is_booked:
                return self.driver

            else:
                time.sleep(randint(2, 4))
                self.refresh_result()

    def send_email(self, message):

        title = "[자동화] SRT 예매 성공 알림"
        content = f"{message}\n\n10분 내에 결제하지 않으면 취소됩니다."

        msg = MIMEText(content)
        msg['Subject'] = title
        msg['From'] = self.gmail_send
        msg['To'] = self.gmail_receive

        try:
            # 지메일 SMTP 서버 연결 (보안 연결)
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(self.gmail_send, self.gmail_app_pw)
                smtp.send_message(msg)
            print("이메일 전송 성공!")
        except Exception as e:
            print(f"이메일 전송 실패: {e}")

    def run(self, login_id, login_psw):
        self.run_driver()
        self.set_log_info(login_id, login_psw)
        self.login()
        self.go_search()
        self.check_result()