import { useState, useRef } from 'react'

interface ContractInputProps {
  onSubmit: (text: string) => void
}

const DEMO_CONTRACT = `租赁合同

甲方（出租方）：张三
乙方（承租方）：李四

第一条 租赁标的
甲方将位于北京市朝阳区某小区1号楼1001室的房屋出租给乙方使用，该房屋建筑面积85平方米。

第二条 租赁期限
租赁期限自2024年3月1日起至2025年2月28日止，共计12个月。

第三条 租金及支付方式
月租金为人民币8500元，乙方应于每月1日前以银行转账方式支付。逾期付款的，每逾期一日加收0.5%滞纳金。

第四条 押金
乙方应在签署本合同之日向甲方支付押金人民币17000元。押金在租期届满且乙方无任何损坏时由甲方全额退还。

第五条 违约责任
任意一方提前解约需支付两个月租金作为违约金。

第六条 争议解决
本合同履行过程中发生的争议，双方应协商解决；协商不成的，向房屋所在地人民法院提起诉讼。`

export function ContractInput({ onSubmit }: ContractInputProps) {
  const [text, setText] = useState(DEMO_CONTRACT)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const content = ev.target?.result as string
      if (content) setText(content)
    }
    reader.readAsText(file)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    onSubmit(text.trim())
  }

  return (
    <form className="contract-input" onSubmit={handleSubmit}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="请粘贴合同文本..."
        spellCheck={false}
      />
      <div className="contract-input-actions">
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt"
          onChange={handleFileChange}
        />
        <button type="submit" disabled={!text.trim()}>
          开始审查
        </button>
      </div>
    </form>
  )
}
