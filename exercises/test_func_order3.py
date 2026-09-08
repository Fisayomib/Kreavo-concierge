from func_order3_2 import summ

babz = {"Fisayo": 21, "Fisol": 19, "Fisope": 17}
emp = {}


def test_summ():
    assert summ(babz) == 57
    assert summ(emp) == 0