""" Quickstart script for InstaPy usage """

# imports
from srt_reservation.main import SRT
from srt_reservation.util import parse_cli_args


if __name__ == "__main__":
    cli_args = parse_cli_args()

    login_id = "1234"
    login_psw = "1234"
    dpt_stn = "울산(통도사)"
    arr_stn = "수서"
    dpt_dt = "20251126"
    dpt_tm = "04" # should be even number 짝수

    order_trains_to_check = [1,2] # order of trains to reserve 몇번째 기차 예매할지
    want_reserve = True # ignore it
    slack_token = "$slack_token" # you can just leave it

    srt = SRT(dpt_stn, arr_stn, dpt_dt, dpt_tm, order_trains_to_check, want_reserve, slack_token)
    srt.run(login_id, login_psw)