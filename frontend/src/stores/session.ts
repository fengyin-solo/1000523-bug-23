import { defineStore } from 'pinia'

export type Account = { name: string; station: string }

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '王建国',
    station: '望江站',
    accounts: [{ name: '王建国', station: '望江站' }] as Account[],
    shiftLabel: '白班 08:00-20:00',
    scope: '轨道交通信号设备检修平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setAccounts(list: Account[]) {
      this.accounts = list
    },
    switchAccount(name: string) {
      const account = this.accounts.find((item) => item.name === name)
      if (account) {
        this.operator = account.name
        this.station = account.station
      }
    },
  },
})
