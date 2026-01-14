
from des.min_value_priority_queue import MinValuePriorityQueue


def test_empty_on_new_queue():
    q = MinValuePriorityQueue()
    # empty() should be True when the queue has no elements
    assert q.empty() is True


def test_empty_when_non_empty():
    q = MinValuePriorityQueue()
    q.enqueue(1)
    # empty() should be False when the queue has at least one element
    assert q.empty() is False

