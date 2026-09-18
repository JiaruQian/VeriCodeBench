char to_upper_ascii(char c) {
  if (c >= 'a' && c <= 'z') {
    return (char)(c - 32);
  }
  return c;
}
