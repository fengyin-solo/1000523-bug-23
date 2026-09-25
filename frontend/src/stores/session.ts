import { defineStore } from 'pinia'

export type StationAccount = {
  station: string
  operator: string
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    // 默认用一个与任何设备都不匹配的只读账号，方便演示越权被拒的口径。
    operator: '值班管理员',
    station: '调度中心',
    shiftLabel: '白班 08:00-20:00',
    scope: '轨道交通信号设备检修平台',
    accounts: [
      { station: '调度中心', operator: '值班管理员' },
      { station: '南京站', operator: '王建国' },
      { station: '南京站', operator: '李志强' },
      { station: '苏州站', operator: '陈海峰' },
      { station: '苏州站', operator: '赵敏' },
    ] as StationAccount[],
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    accountKey: (state) => `${state.station}|${state.operator}`,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setAccount(station: string, operator: string) {
      this.station = station
      this.operator = operator
    },
    // 判断当前账号是否为某条设备的归属责任人；列表据此在只读账号下禁用动作按钮。
    owns(entry: { 所属车站?: unknown; 责任人?: unknown }): boolean {
      return String(entry.所属车站 ?? '') === this.station
        && String(entry.责任人 ?? '') === this.operator
    },
  },
})
