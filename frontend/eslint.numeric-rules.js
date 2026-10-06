// Keep exact API decimals out of JavaScript floating-point numbers.
//
// The API sends measurements as strings such as "100056.000000". A float can
// change such a value: Number("0.1") + Number("0.2") is 0.30000000000000004.
// These conversions are therefore errors in application code. Use the scaled
// BigInt helpers in src/lib/decimal.ts instead. parseInt stays allowed for
// integer HTTP headers such as Retry-After, after a strict digit check.
const message = 'Keep API decimals as strings. Use src/lib/decimal.ts for exact arithmetic.'

export const exactNumberRules = {
  rules: {
    'no-restricted-globals': ['error', { name: 'parseFloat', message }],
    'no-restricted-properties': ['error', { object: 'Number', property: 'parseFloat', message }],
    'no-restricted-syntax': [
      'error',
      { selector: "CallExpression[callee.name='Number']", message },
      { selector: "NewExpression[callee.name='Number']", message },
      { selector: "UnaryExpression[operator='+']", message: `Unary + converts text to a float. ${message}` },
    ],
  },
}
