const {test} = require('node:test');
const assert = require('node:assert/strict');
const {normalizeAddress} = require('../www/connection.js');

test('normalizes private laptop addresses without losing ports', () => {
  assert.equal(normalizeAddress(' 192.168.1.20 '), 'http://192.168.1.20:8501');
  assert.equal(normalizeAddress('10.217.38.223:8501'), 'http://10.217.38.223:8501');
  assert.equal(normalizeAddress('http://172.16.0.1:8000/'), 'http://172.16.0.1:8000');
  assert.equal(normalizeAddress('https://172.31.1.2'), 'https://172.31.1.2');
});
test('rejects destinations that are not a private laptop origin', () => {
  for (const value of ['', 'localhost:8501', '127.0.0.1', '172.15.0.1', '172.32.0.1', '8.8.8.8', 'https://example.com', 'file:///data/a', 'javascript:alert(1)', '192.168.1.999', '10.1', '0x0a000001', '010.1.1.1', '192.168.1.1:0', '192.168.1.1:65536', 'http://user:password@192.168.1.2', '192.168.1.2/path', '192.168.1.2?x=1', '192.168.1.2#token', 'http://10.evil.example', 'http://192.168.1.2\\@evil.example']) {
    assert.equal(normalizeAddress(value), null, value);
  }
});
