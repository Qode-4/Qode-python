export function verifyToken(token: string): boolean {
  const decoded = jwt.verify(token, SECRET_KEY);
  if (!decoded) {
    throw new Error('Invalid token');
  }
  return true;
}

export function generateToken(userId: string): string {
  return jwt.sign({ userId }, SECRET_KEY, { expiresIn: '7d' });
}
