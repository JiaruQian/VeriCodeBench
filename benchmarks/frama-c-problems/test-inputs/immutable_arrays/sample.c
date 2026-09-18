int fun(int x, int y) {
    int r = x;
    int d = 0;
    while (r >= y) {
        r = r - y;
        d = d + 1;
    }
    return d;
}
