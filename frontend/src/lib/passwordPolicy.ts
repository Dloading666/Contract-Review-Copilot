export const PASSWORD_POLICY_MESSAGE = '密码必须至少 8 位，并包含大写字母、小写字母和数字'

const PASSWORD_POLICY_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/

export function getPasswordValidationError(password: string): string | null {
  const normalizedPassword = password.trim()
  if (!normalizedPassword) {
    return '请输入密码'
  }
  if (!PASSWORD_POLICY_PATTERN.test(normalizedPassword)) {
    return PASSWORD_POLICY_MESSAGE
  }
  return null
}
